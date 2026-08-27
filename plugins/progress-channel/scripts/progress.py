#!/usr/bin/env python3
"""progress-channel — one visible channel for every long-running process.

Library:  from progress import Job
    with Job('video integrity', total=10453) as j:
        for item in items:
            j.step(detail=item, ok=1)

CLI:      python3 progress.py daemon|list|watch|forecast|run|mirror|prune

Architecture: the thing that serves the progress page IS the tracker. A tiny
stdlib HTTP daemon on 127.0.0.1 holds live jobs **in memory** (single
writer — no store locking at all), serves the HTML view at /, and actively
sweeps for orphans by checking producer pids directly (it is local, so no
heartbeat protocol is needed). Producers auto-spawn it on first use; binding
the port is the single-instance lease.

Only what must survive a restart is persisted: finished runs append to
~/.claude/progress/history.jsonl (the learning data — cat/jq-able, no
database). Live state is memory-only on purpose: producers re-register on
their next flush if the daemon restarts, and a reboot kills the jobs anyway.

Design constraints carried from the #36 review: the job is a context manager
(a crash records a failure, never a forever-running row); step() flushes on
a throttle, not per item; duration history is keyed by (name, kind,
total-bucket) and capped; ETA cuts over from history to the current run's
own rate as progress accumulates; the viewer derives liveness
(orphaned/stalled) instead of trusting `running`. A job must never fail
because the tracker is sick: if the daemon cannot be reached or spawned,
producers degrade to a warn-once no-op.
"""
from __future__ import annotations

import json
import os
import re
import statistics
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Tunables. Constants, not config: the channel must behave identically for
# every producer or the view stops being trustworthy.
DEFAULT_PORT = 7717
FLUSH_EVERY_STEPS = 50
FLUSH_EVERY_SECONDS = 1.0
HISTORY_KEEP = 20            # runs kept per (name, kind, total_bucket)
FINISHED_KEEP_HOURS = 24     # finished jobs shown in the view this long
ETA_CUTOVER_FRACTION = 0.10  # current-run rate fully trusted past this progress
STALL_GAP_FACTOR = 3.0       # stalled when silent > factor * learned p95 gap
STALL_GAP_FLOOR = 30.0       # ... but never call a gap under this a stall


def home() -> Path:
    return Path(os.environ.get("PROGRESS_HOME",
                               str(Path.home() / ".claude" / "progress")))


def port() -> int:
    return int(os.environ.get("PROGRESS_PORT", DEFAULT_PORT))


def base_url() -> str:
    return f"http://127.0.0.1:{port()}"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def total_bucket(total: int | None) -> int:
    """Order-of-magnitude shape key: 10k videos and 200k thumbnails under one
    name must not blend into one meaningless per-item median."""
    return len(str(int(total))) if total else 0


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _percentile(values: list[float], p: float) -> float:
    vs = sorted(values)
    idx = min(len(vs) - 1, max(0, int(round(p * (len(vs) - 1)))))
    return vs[idx]


# ── history (the only persisted state) ─────────────────────────────────────

def _shape(rec: dict) -> tuple:
    return (rec.get("name"), rec.get("kind"), rec.get("total_bucket", 0))


def load_history() -> list[dict]:
    path = home() / "history.jsonl"
    rows: list[dict] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def append_history(rec: dict) -> None:
    path = home() / "history.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def compact_history(rows: list[dict]) -> list[dict]:
    """Retention: an ETA input, not an archive — last N runs per shape."""
    by_shape: dict[tuple, list[dict]] = {}
    for r in rows:
        by_shape.setdefault(_shape(r), []).append(r)
    kept: list[dict] = []
    for shape_rows in by_shape.values():
        shape_rows.sort(key=lambda r: r.get("finished_at", ""))
        kept.extend(shape_rows[-HISTORY_KEEP:])
    kept.sort(key=lambda r: r.get("finished_at", ""))
    return kept


def hist_per_item(rows: list[dict], name, kind, bucket) -> float | None:
    vals = [r["per_item"] for r in rows
            if _shape(r) == (name, kind, bucket)
            and r.get("status") == "done" and r.get("per_item")]
    return statistics.median(vals[-HISTORY_KEEP:]) if vals else None


def hist_p95_gap(rows: list[dict], name) -> float | None:
    vals = [r["p95_gap"] for r in rows
            if r.get("name") == name and r.get("status") == "done"
            and r.get("p95_gap")]
    return statistics.median(vals[-HISTORY_KEEP:]) if vals else None


def forecast_text(rows: list[dict], name: str) -> str:
    secs = [r["seconds"] for r in rows
            if r.get("name") == name and r.get("status") == "done"
            and r.get("seconds")]
    if not secs:
        return f"{name}: no history — first run has no estimate."
    lo, hi = _percentile(secs, 0.25), _percentile(secs, 0.75)
    return (f"{name}: {_fmt_dur(lo)}–{_fmt_dur(hi)} over the last "
            f"{len(secs)} successful run(s) (median {_fmt_dur(statistics.median(secs))}).")


# ── daemon ─────────────────────────────────────────────────────────────────

class Tracker:
    """In-memory channel state. The HTTP handler and the sweep thread are
    the only writers; one lock keeps them honest."""

    def __init__(self):
        self.lock = threading.Lock()
        self.jobs: dict[str, dict] = {}       # uid -> live job dict
        self.finished: list[dict] = []        # recent finished, view only
        self.history = compact_history(load_history())
        self.host = os.uname().nodename

    def upsert(self, rec: dict) -> None:
        uid = rec["uid"]
        with self.lock:
            job = self.jobs.get(uid, {})
            job.update(rec)
            job["updated_at"] = _now()
            job.setdefault("started_at", job["updated_at"])
            if job.get("status", "running") != "running":
                self.jobs.pop(uid, None)
                job.setdefault("finished_at", job["updated_at"])
                self.finished.append(job)
                self._record_history(job)
            else:
                self.jobs[uid] = job

    def _record_history(self, job: dict) -> None:
        rec = {
            "name": job.get("name"), "kind": job.get("kind"),
            "total_bucket": total_bucket(job.get("total")),
            "total": job.get("total"), "done": job.get("done", 0),
            "seconds": job.get("seconds"), "per_item": job.get("per_item"),
            "p95_gap": job.get("p95_gap"), "status": job.get("status"),
            "host": job.get("host"), "finished_at": job["finished_at"],
        }
        self.history.append(rec)
        append_history(rec)

    def sweep(self) -> None:
        """Active orphan detection: the daemon is local, so it checks the
        producer's pid directly — a running job whose process died too hard
        for __exit__ is adjudicated here, not trusted forever."""
        with self.lock:
            for uid, job in list(self.jobs.items()):
                if job.get("host") == self.host and not pid_alive(job.get("pid")):
                    job["status"] = "orphaned"
                    job["error"] = "no __exit__: process died"
                    job["finished_at"] = _now()
                    self.jobs.pop(uid)
                    self.finished.append(job)
                    self._record_history(job)
            cutoff = datetime.now(timezone.utc) - timedelta(hours=FINISHED_KEEP_HOURS)
            self.finished = [
                j for j in self.finished
                if (_parse_ts(j.get("finished_at")) or datetime.now(timezone.utc)) > cutoff
            ][-60:]

    # -- view-side derivation ---------------------------------------------
    def classify(self, job: dict) -> str:
        if job.get("status", "running") != "running":
            return job["status"]
        if job.get("host") == self.host and not pid_alive(job.get("pid")):
            return "orphaned"
        updated = _parse_ts(job.get("updated_at"))
        if updated is not None:
            silent = (datetime.now(timezone.utc) - updated).total_seconds()
            p95 = hist_p95_gap(self.history, job.get("name"))
            if p95 is not None and silent > max(STALL_GAP_FACTOR * p95,
                                                STALL_GAP_FLOOR):
                return "stalled"
        return "running"

    def eta_seconds(self, job: dict) -> float | None:
        """Pre-cutover the history median predicts; as the run's own evidence
        accumulates its observed rate takes over (blend by progress)."""
        total, done = job.get("total"), job.get("done", 0)
        if not total or done <= 0:
            return None
        started = _parse_ts(job.get("started_at"))
        if started is None:
            return None
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        current = elapsed / done
        hist = hist_per_item(self.history, job.get("name"), job.get("kind"),
                             total_bucket(total))
        if hist is not None:
            w = min(1.0, (done / total) / ETA_CUTOVER_FRACTION)
            rate = w * current + (1 - w) * hist
        else:
            rate = current
        return max(0, total - done) * rate

    def snapshot(self) -> list[dict]:
        with self.lock:
            rows = []
            live = sorted(self.jobs.values(),
                          key=lambda j: j.get("updated_at", ""), reverse=True)
            done = sorted(self.finished,
                          key=lambda j: j.get("finished_at", ""), reverse=True)
            for job in live + done:
                out = dict(job)
                out["state"] = self.classify(job)
                out["eta_seconds"] = self.eta_seconds(job) \
                    if out["state"] == "running" else None
                rows.append(out)
            return rows


PAGE = """<!doctype html><meta charset="utf-8"><title>progress</title>
<style>
 body{font:14px/1.5 monospace;margin:2em auto;max-width:64em;background:#111;color:#ddd}
 h1{font-size:1.1em;color:#8ac} table{border-collapse:collapse;width:100%}
 td,th{padding:.25em .6em;text-align:left;border-bottom:1px solid #333}
 .running{color:#8c8}.done{color:#666}.failed{color:#e77}.orphaned{color:#e77}
 .stalled{color:#eb6}.bar{background:#333;height:.5em;min-width:8em}
 .bar>div{background:#8ac;height:100%}
 small{color:#777}
</style>
<h1>progress <small id="ts"></small></h1>
<table><thead><tr><th>job</th><th>state</th><th>progress</th><th>eta</th>
<th>counters</th><th>detail</th></tr></thead><tbody id="rows"></tbody></table>
<script>
function dur(s){if(s==null)return"";s=Math.round(s);
 if(s<60)return s+"s";if(s<3600)return Math.floor(s/60)+"m"+String(s%60).padStart(2,"0")+"s";
 return Math.floor(s/3600)+"h"+String(Math.floor(s%3600/60)).padStart(2,"0")+"m"}
async function tick(){try{
 const r=await fetch("/jobs");const d=await r.json();
 document.getElementById("ts").textContent=d.now;
 document.getElementById("rows").innerHTML=d.jobs.map(j=>{
  const pct=j.total?Math.min(100,100*j.done/j.total):null;
  const bar=pct==null?j.done:`<div class="bar"><div style="width:${pct}%"></div></div>${j.done}/${j.total}`;
  const c=j.counters?Object.entries(j.counters).map(([k,v])=>k+"="+v).join(" "):"";
  return `<tr class="${j.state}"><td>${j.name}</td><td>${j.state}</td>`+
   `<td>${bar}</td><td>${dur(j.eta_seconds)}</td><td>${c}</td>`+
   `<td>${j.detail||j.error||""}</td></tr>`}).join("");
}catch(e){}}
tick();setInterval(tick,2000);
</script>"""


def run_daemon(bind_port: int | None = None,
               sweep_interval: float | None = None) -> None:
    tracker = Tracker()
    interval = sweep_interval if sweep_interval is not None else float(
        os.environ.get("PROGRESS_SWEEP", "2.0"))

    def sweeper():
        while True:
            time.sleep(interval)
            tracker.sweep()

    threading.Thread(target=sweeper, daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200) -> None:
            self._send(code, json.dumps(obj).encode(), "application/json")

        def do_GET(self):
            path = urllib.parse.urlparse(self.path)
            if path.path == "/":
                self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            elif path.path == "/health":
                self._json({"ok": True, "pid": os.getpid()})
            elif path.path == "/jobs":
                self._json({"now": _now(), "jobs": tracker.snapshot()})
            elif path.path == "/forecast":
                name = urllib.parse.parse_qs(path.query).get("name", [""])[0]
                self._json({"text": forecast_text(tracker.history, name)})
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            if self.path != "/jobs":
                self._json({"error": "not found"}, 404)
                return
            length = int(self.headers.get("Content-Length", 0))
            try:
                rec = json.loads(self.rfile.read(length))
                if not isinstance(rec, dict) or "uid" not in rec:
                    raise ValueError("job record needs a uid")
            except (json.JSONDecodeError, ValueError) as e:
                self._json({"error": str(e)}, 400)
                return
            tracker.upsert(rec)
            self._json({"ok": True})

    srv = ThreadingHTTPServer(("127.0.0.1", bind_port or port()), Handler)
    print(f"progress daemon on {base_url()} (history: {home() / 'history.jsonl'})")
    srv.serve_forever()


# ── producer side ──────────────────────────────────────────────────────────

def _post_job(rec: dict, timeout: float = 1.0) -> bool:
    req = urllib.request.Request(
        base_url() + "/jobs", data=json.dumps(rec).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
        return False


def _get_json(path: str, timeout: float = 2.0) -> dict | None:
    try:
        with urllib.request.urlopen(base_url() + path, timeout=timeout) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, ConnectionError, TimeoutError,
            OSError, json.JSONDecodeError):
        return None


_spawn_attempted = False


def ensure_daemon() -> bool:
    """Auto-spawn: producers never require a separately-managed service.
    Binding the port is the single-instance lease, so a lost race is a win
    (someone else's daemon answers). One spawn attempt per process."""
    global _spawn_attempted
    if _get_json("/health", timeout=0.5):
        return True
    if _spawn_attempted:
        return False
    _spawn_attempted = True
    home().mkdir(parents=True, exist_ok=True)
    log = open(home() / "daemon.log", "ab")
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "daemon"],
                     stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                     start_new_session=True, env=os.environ.copy())
    for _ in range(30):
        time.sleep(0.1)
        if _get_json("/health", timeout=0.5):
            return True
    return False


class Job:
    """Context-managed progress record. Exiting on an exception reports a
    failure; only SIGKILL-class deaths go silent, and the daemon's pid sweep
    catches those. If the daemon can't be reached or spawned, the job runs
    as a warn-once no-op — work never fails because the tracker is sick."""

    def __init__(self, name: str, total: int | None = None, kind: str = "local",
                 source: str | None = None, detail: str | None = None,
                 project: str | None = None):
        self.name, self.total, self.kind = name, total, kind
        self.source, self.detail = source, detail
        self.project = project or os.path.basename(os.getcwd())
        self.uid = uuid.uuid4().hex
        self.done = 0
        self.counters: dict[str, int] = {}
        self._connected = False
        self._steps_since_flush = 0
        self._last_flush = 0.0
        self._last_step: float | None = None
        self._gaps: list[float] = []
        self._t0 = 0.0

    def _record(self, status: str = "running", error: str | None = None,
                seconds: float | None = None) -> dict:
        rec = {
            "uid": self.uid, "name": self.name, "kind": self.kind,
            "source": self.source, "project": self.project,
            "total": self.total, "done": self.done, "status": status,
            "detail": self.detail,
            "counters": self.counters or None,
            "pid": os.getpid(), "host": os.uname().nodename,
        }
        if status != "running":
            rec["error"] = error
            rec["seconds"] = seconds
            rec["per_item"] = (seconds / self.done) if self.done and seconds else None
            rec["p95_gap"] = _percentile(self._gaps, 0.95) \
                if len(self._gaps) >= 5 else None
        return rec

    def __enter__(self) -> "Job":
        self._connected = ensure_daemon()
        if not self._connected:
            print(f"progress: daemon unreachable — '{self.name}' untracked",
                  file=sys.stderr)
        self._t0 = time.monotonic()
        self._last_flush = self._t0
        self._flush()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        status = "failed" if exc_type else "done"
        error = f"{exc_type.__name__}: {exc}"[:500] if exc_type else None
        self._flush(status=status, error=error,
                    seconds=time.monotonic() - self._t0)
        return False  # never swallow the exception

    def step(self, n: int = 1, detail: str | None = None, **counters: int) -> None:
        now = time.monotonic()
        if self._last_step is not None:
            self._gaps.append(now - self._last_step)
        self._last_step = now
        self.done += n
        if detail is not None:
            self.detail = detail
        for k, v in counters.items():
            self.counters[k] = self.counters.get(k, 0) + int(v)
        self._steps_since_flush += n
        if (self._steps_since_flush >= FLUSH_EVERY_STEPS
                or now - self._last_flush >= FLUSH_EVERY_SECONDS):
            self._flush()

    def set_total(self, total: int) -> None:
        self.total = total
        self._flush()

    def _flush(self, status: str = "running", error: str | None = None,
               seconds: float | None = None) -> None:
        self._steps_since_flush = 0
        self._last_flush = time.monotonic()
        if not self._connected:
            return
        # A mid-run daemon restart just means the next flush re-registers —
        # the producer is the source of truth for its own job.
        self._connected = _post_job(self._record(status, error, seconds)) \
            or ensure_daemon() and _post_job(self._record(status, error, seconds))


# ── CLI ────────────────────────────────────────────────────────────────────

def _fmt_dur(s: float | None) -> str:
    if s is None:
        return "?"
    s = int(s)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


def _fmt_row(j: dict) -> str:
    state = j.get("state", j.get("status", "?"))
    frac = (f"{j.get('done', 0)}/{j['total']}" if j.get("total")
            else str(j.get("done", 0)))
    eta = f" eta {_fmt_dur(j['eta_seconds'])}" if j.get("eta_seconds") else ""
    counters = ""
    if j.get("counters"):
        counters = " " + " ".join(f"{k}={v}" for k, v in j["counters"].items())
    detail = f" · {j['detail']}" if j.get("detail") else ""
    err = f" · {j['error']}" if j.get("error") else ""
    mark = {"running": "▶", "done": "✓", "failed": "✗", "orphaned": "☠",
            "stalled": "⏸", "cancelled": "∅"}.get(state, "?")
    return (f"{mark} {j.get('name', '?'):32.32} {state:9} {frac:>13}{eta}"
            f"{counters}{detail}{err}")


def cmd_list() -> list[str]:
    if not _get_json("/health", timeout=0.5):
        return [f"(no daemon on {base_url()} — nothing tracked; it starts"
                " with the first job)"]
    data = _get_json("/jobs")
    if not data:
        return ["(daemon unreachable)"]
    return [_fmt_row(j) for j in data["jobs"]] or ["(no jobs)"]


def cmd_watch(interval: float) -> None:
    try:
        while True:
            lines = cmd_list()
            sys.stdout.write("\x1b[2J\x1b[H")
            print(f"progress · {base_url()} · {_now()}  (ctrl-c to quit)\n")
            print("\n".join(lines))
            sys.stdout.flush()
            time.sleep(interval)
    except KeyboardInterrupt:
        pass


def cmd_run(argv: list[str]) -> int:
    """Wrap an arbitrary command as a job: no per-item granularity, but the
    run lands in the channel and its duration feeds the forecast."""
    import argparse
    ap = argparse.ArgumentParser(prog="progress run")
    ap.add_argument("--name", required=True)
    ap.add_argument("--kind", default="background")
    ap.add_argument("--total", type=int)
    ap.add_argument("cmd", nargs="+")
    a = ap.parse_args(argv)
    with Job(a.name, total=a.total, kind=a.kind,
             detail=" ".join(a.cmd)[:120]) as j:
        rc = subprocess.call(a.cmd)
        if rc != 0:
            raise RuntimeError(f"exit code {rc}")
        if a.total:
            j.done = a.total
    return rc


def cmd_mirror(argv: list[str]) -> int:
    """Watcher for work we did not start and cannot instrument. Polls a
    status command, mirrors its numbers into the channel, exits when idle.
    The live job (its pid checked by the daemon sweep) is the lease: a
    second mirror for the same source refuses to start."""
    import argparse
    ap = argparse.ArgumentParser(prog="progress mirror")
    ap.add_argument("--name", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--poll-cmd", required=True,
                    help="shell command printing '<done> <total>', '<done>', or 'idle'")
    ap.add_argument("--interval", type=float, default=30)
    ap.add_argument("--idle-after", type=int, default=2,
                    help="consecutive idle polls before the watcher exits")
    a = ap.parse_args(argv)

    ensure_daemon()
    data = _get_json("/jobs") or {"jobs": []}
    for j in data["jobs"]:
        if (j.get("source") == a.source and j.get("state") == "running"):
            print(f"refusing: live watcher pid={j.get('pid')} already mirrors"
                  f" source '{a.source}'", file=sys.stderr)
            return 3

    idle = 0
    with Job(a.name, kind="external", source=a.source) as j:
        while idle < a.idle_after:
            out = subprocess.run(a.poll_cmd, shell=True, capture_output=True,
                                 text=True, timeout=60).stdout.strip()
            m = re.match(r"^(\d+)(?:\s+(\d+))?", out)
            if out.lower().startswith("idle") or not m:
                idle += 1
            else:
                idle = 0
                j.done = int(m.group(1))
                if m.group(2):
                    j.total = int(m.group(2))
                if j.total and j.done >= j.total:
                    idle = a.idle_after
            j.step(0)  # heartbeat flush: updates the row without inflating done
            j._flush()
            if idle < a.idle_after:
                time.sleep(a.interval)
    return 0


def cmd_prune() -> int:
    rows = load_history()
    kept = compact_history(rows)
    path = home() / "history.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in kept),
                    encoding="utf-8")
    print(f"history: {len(rows)} -> {len(kept)} row(s)")
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    verb, rest = argv[0], argv[1:]
    if verb == "daemon":
        run_daemon()
        return 0
    if verb == "run":
        return cmd_run(rest)
    if verb == "mirror":
        return cmd_mirror(rest)
    if verb == "list":
        print("\n".join(cmd_list()))
        return 0
    if verb == "watch":
        interval = float(rest[rest.index("--interval") + 1]) \
            if "--interval" in rest else 2.0
        cmd_watch(interval)
        return 0
    if verb == "forecast":
        if not rest:
            print("usage: progress forecast <name>", file=sys.stderr)
            return 2
        data = _get_json("/forecast?name=" + urllib.parse.quote(rest[0]))
        print(data["text"] if data else forecast_text(load_history(), rest[0]))
        return 0
    if verb == "prune":
        return cmd_prune()
    print(f"unknown verb: {verb}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
