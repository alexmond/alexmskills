#!/usr/bin/env python3
"""progress-channel — one visible channel for every long-running process.

Library:  from progress import Job
    with Job('video integrity', total=10453) as j:
        for item in items:
            j.step(detail=item, ok=1)

CLI:      python3 progress.py daemon|list|watch|forecast|run|mirror|prune
Shell:    T=$(progress.py start --name 'photo import' --total 800)
          progress.py step $T --count ok=1        # in the loop
          progress.py finish $T                   # or: finish $T --fail "why"

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
import math
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
# Two different clocks, deliberately. REMOVAL is when a finished row leaves the
# store for good (it is still queryable with ?state=all until then). LINGER is
# how long it keeps appearing in the LIVE view next to running work — long
# enough to see a job land on 100%, short enough that the view stays about what
# is happening now.
FINISHED_KEEP_HOURS = 24     # removal: done/failed rows are dropped after this
DONE_LINGER_SECONDS = 20     # visibility: finished rows stay in the live view
ORPHAN_KEEP_MINUTES = 30     # orphans are already dead — a much shorter leash
FINISHED_KEEP_MAX = 60       # hard cap, so a busy day cannot grow the view
LIVE_STATES = ("running", "stalled")   # what /jobs returns when no state is asked for
ETA_CUTOVER_FRACTION = 0.10  # current-run rate fully trusted past this progress
STALL_GAP_FACTOR = 3.0       # stalled when silent > factor * learned p95 gap
STALL_GAP_FLOOR = 30.0       # ... but never call a gap under this a stall


def home() -> Path:
    return Path(os.environ.get("PROGRESS_HOME",
                               str(Path.home() / ".claude" / "progress")))


def port() -> int:
    return int(os.environ.get("PROGRESS_PORT", DEFAULT_PORT))


def _expiry() -> tuple[float, float, int]:
    """(finished hours, orphan minutes, hard cap) — env-tunable so an operator
    can change retention without editing the plugin."""
    return (float(os.environ.get("PROGRESS_FINISHED_HOURS", FINISHED_KEEP_HOURS)),
            float(os.environ.get("PROGRESS_ORPHAN_MINUTES", ORPHAN_KEEP_MINUTES)),
            int(os.environ.get("PROGRESS_FINISHED_MAX", FINISHED_KEEP_MAX)))


def _linger_seconds() -> float:
    return float(os.environ.get("PROGRESS_DONE_LINGER", DONE_LINGER_SECONDS))


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


def hist_median_seconds(rows: list[dict], name, kind) -> float | None:
    """Median wall-clock duration of past runs of this job. Used to fill a
    time-based bar when the caller did not declare an expected duration."""
    vals = [r["seconds"] for r in rows
            if r.get("name") == name and r.get("kind") == kind
            and r.get("status") == "done" and r.get("seconds")]
    return statistics.median(vals[-HISTORY_KEEP:]) if vals else None


def session_identity() -> tuple[str | None, str | None, str | None]:
    """(session id, session name, agent) of the work that owns this job.

    A subagent runs under its parent's CLAUDE_CODE_SESSION_ID, which is what
    you want — its work belongs to your session and should show in your status
    line. CLAUDE_CODE_AGENT is set only inside a subagent, so it is the one
    thing that distinguishes "the main loop is doing this" from "an agent I
    spawned is doing this".

    Claude Code exports CLAUDE_CODE_SESSION_ID into every tool process, so a
    producer started by a session inherits it with nothing to plumb through.
    Work started outside a session — cron, a bare shell — carries None and
    appears only in the unfiltered view.
    """
    return (os.environ.get("CLAUDE_CODE_SESSION_ID") or None,
            os.environ.get("CLAUDE_CODE_SESSION_NAME") or None,
            os.environ.get("CLAUDE_CODE_AGENT") or None)


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
    text = (f"{name}: {_fmt_dur(lo)}–{_fmt_dur(hi)} over the last "
            f"{len(secs)} successful run(s) (median {_fmt_dur(statistics.median(secs))}).")
    label, pct = trend(rows, name)
    if label != "stable":
        text += f" Trend: {label} {pct:+.0f}%."
    return text


def trend(rows: list[dict], name: str) -> tuple[str, float]:
    """Change-over-runs signal: recent runs vs the older baseline of the
    same shape. 'slowing +40%' is a lesson a bare counter can never give."""
    mine = [r for r in rows if r.get("name") == name
            and r.get("status") == "done" and r.get("seconds")]
    if len(mine) < 4:
        return "stable", 0.0
    shape = _shape(mine[-1])
    secs = [r["seconds"] for r in mine if _shape(r) == shape]
    if len(secs) < 4:
        return "stable", 0.0
    recent = statistics.median(secs[-2:])
    base = statistics.median(secs[:-2])
    if base <= 0:
        return "stable", 0.0
    pct = (recent / base - 1.0) * 100
    if pct >= 25:
        return "slowing", pct
    if pct <= -20:
        return "improving", pct
    return "stable", pct


def history_summary(rows: list[dict]) -> list[dict]:
    """Per-name digest for the page: recent durations + trend."""
    by_name: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("status") == "done" and r.get("seconds"):
            by_name.setdefault(r["name"], []).append(r)
    out = []
    for name, runs in by_name.items():
        secs = [r["seconds"] for r in runs][-HISTORY_KEEP:]
        label, pct = trend(rows, name)
        out.append({"name": name, "runs": len(runs), "seconds": secs,
                    "median": statistics.median(secs),
                    "trend": label, "trend_pct": round(pct, 1),
                    "last_finished": runs[-1].get("finished_at")})
    out.sort(key=lambda d: d["last_finished"] or "", reverse=True)
    return out


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
            prev_done = job.get("done")
            job.update(rec)
            job["updated_at"] = _now()
            job.setdefault("started_at", job["updated_at"])
            # done_at is when the COUNT last moved, which is not the same as
            # updated_at (a ping or a detail change bumps that too). The ETA
            # needs the former: rate must come from completed work only.
            if job.get("done") != prev_done:
                job["done_at"] = job["updated_at"]
            job.setdefault("done_at", job["started_at"])
            job.pop("_stall_notified", None)  # activity resets the stall episode
            if job.get("status", "running") != "running":
                self.jobs.pop(uid, None)
                job.setdefault("finished_at", job["updated_at"])
                self.finished.append(job)
                self._record_history(job)
                self._notify(job, job["status"])
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
                    self._notify(job, "orphaned")
                elif self.classify(job) == "stopped":
                    job["status"] = "stopped"
                    job["error"] = ("no ping within %ss" % job.get("ping_timeout"))
                    job["finished_at"] = _now()
                    self.jobs.pop(uid)
                    self.finished.append(job)
                    self._record_history(job)
                    self._notify(job, "stopped")
                elif (not job.get("_stall_notified")
                        and self.classify(job) == "stalled"):
                    job["_stall_notified"] = True  # once per stall episode
                    self._notify(job, "stalled")
            # Expiry. An orphan is a job whose producer died — it is already
            # over, and keeping it for a day just buries the live rows under
            # wreckage. done/failed stay longer because you look them up on
            # purpose ("did the nightly pass?"); orphans you look at now or
            # never. The hard cap bounds a pathological day either way.
            now = datetime.now(timezone.utc)
            fin_hours, orph_minutes, keep_max = _expiry()
            fin_cutoff = now - timedelta(hours=fin_hours)
            orph_cutoff = now - timedelta(minutes=orph_minutes)

            def _unexpired(j: dict) -> bool:
                ts = _parse_ts(j.get("finished_at")) or now
                return ts > (orph_cutoff if j.get("status") == "orphaned"
                             else fin_cutoff)

            self.finished = [j for j in self.finished if _unexpired(j)][-keep_max:]

    def _notify(self, job: dict, event: str) -> None:
        """User hook: an executable at ~/.claude/progress/notify is the whole
        configuration. It runs detached with the event in env vars, so it can
        be notify-send, gmail-send, or anything else — the daemon never
        waits on it and never fails because of it."""
        hook = home() / "notify"
        if not (hook.is_file() and os.access(hook, os.X_OK)):
            return
        env = os.environ.copy()
        env.update({
            "PROGRESS_EVENT": event,
            "PROGRESS_NAME": str(job.get("name") or ""),
            "PROGRESS_STATUS": str(job.get("status") or ""),
            "PROGRESS_DONE": str(job.get("done") or 0),
            "PROGRESS_TOTAL": str(job.get("total") or ""),
            "PROGRESS_SECONDS": str(job.get("seconds") or ""),
            "PROGRESS_ERROR": str(job.get("error") or ""),
            "PROGRESS_PROJECT": str(job.get("project") or ""),
        })
        try:
            subprocess.Popen([str(hook)], env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,
                             start_new_session=True)
        except OSError:
            pass

    # -- view-side derivation ---------------------------------------------
    def classify(self, job: dict) -> str:
        if job.get("status", "running") != "running":
            return job["status"]
        if job.get("host") == self.host and not pid_alive(job.get("pid")):
            return "orphaned"
        updated = _parse_ts(job.get("updated_at"))
        if updated is not None:
            silent = (datetime.now(timezone.utc) - updated).total_seconds()
            # An explicit timeout is a contract the producer opted into, so it
            # outranks the learned stall heuristic and is terminal, not advisory.
            timeout = job.get("ping_timeout")
            if timeout and silent > float(timeout):
                return "stopped"
            p95 = hist_p95_gap(self.history, job.get("name"))
            if p95 is not None and silent > max(STALL_GAP_FACTOR * p95,
                                                STALL_GAP_FLOOR):
                return "stalled"
        return "running"

    def eta_seconds(self, job: dict) -> float | None:
        """Seconds of work left. Pre-cutover the history median predicts; as the
        run's own evidence accumulates its observed rate takes over.

        Two things here exist to stop "time left" counting UP.

        The rate comes from **completed work only** — elapsed at the moment the
        last item landed, over the items that landed. Dividing by *now* instead
        inflates the rate every second the current item is still in flight, so
        the estimate grows between steps; on a 15-item job with slow steps that
        is almost all of the time.

        Then the time already spent on the in-flight item is **subtracted**, so
        the number ticks down in real time instead of holding still between
        steps and jumping at each one. It floors at zero: a job past its own
        estimate reads "any moment now", never negative.
        """
        total, done = job.get("total"), job.get("done", 0)
        if not total or done <= 0:
            return None
        started = _parse_ts(job.get("started_at"))
        if started is None:
            return None
        now = datetime.now(timezone.utc)
        hist = hist_per_item(self.history, job.get("name"), job.get("kind"),
                             total_bucket(total))
        marked = _parse_ts(job.get("done_at"))
        current, in_flight = None, 0.0

        if marked is None:
            # No done_at: a record written before it was tracked, or a synthetic
            # one. Elapsed/done is the only evidence there is — keep the old
            # estimate rather than refusing. Nothing to subtract, so it holds
            # steady rather than ticking down.
            current = max((now - started).total_seconds(), 0.0) / done
        else:
            worked = (marked - started).total_seconds()
            in_flight = max((now - marked).total_seconds(), 0.0)
            if worked > 0:
                current = worked / done
            elif hist is None:
                # Timestamps are second-resolution, so a job whose items have
                # all landed inside one second has no rate of its own yet. Say
                # NOTHING rather than dividing by now — that grows every second
                # the current item is in flight, which is what made the estimate
                # count UP instead of down.
                return None

        if current is None:
            rate = hist
        elif hist is not None:
            w = min(1.0, (done / total) / ETA_CUTOVER_FRACTION)
            rate = w * current + (1 - w) * hist
        else:
            rate = current

        return max(0.0, max(0, total - done) * rate - in_flight)

    def progress(self, job: dict) -> tuple[float | None, str]:
        """(ratio 0..1 or None, mode).

        Computed here, once, so the page, the status line and any other reader
        cannot disagree about what a bar means. Four modes, most-honest first:

          items  done/total — real measurement
          time   elapsed against a duration the caller declared
          eta    elapsed against the median of this job's own past runs
          creep  nothing to measure against: the open-ended curve Claude Code's
                 own /compact bar uses, 1-exp(-t/90), capped so it never ends

        `time` and `eta` cap at 0.99: a job that overruns its estimate must not
        read as finished, because that is exactly when you most want to look.
        """
        status = job.get("status", "running")
        if status != "running":
            return (1.0 if status == "done" else None), status

        total, done = job.get("total"), job.get("done", 0)
        if total:
            return max(0.0, min(1.0, done / total)), "items"

        started = _parse_ts(job.get("started_at"))
        elapsed = (datetime.now(timezone.utc) - started).total_seconds() \
            if started else 0.0
        elapsed = max(0.0, elapsed)

        expect = job.get("expect_seconds")
        if expect and expect > 0:
            return min(0.99, elapsed / expect), "time"

        hist = hist_median_seconds(self.history, job.get("name"), job.get("kind"))
        if hist and hist > 0:
            return min(0.99, elapsed / hist), "eta"

        return min(0.95, 1 - math.exp(-elapsed / 90.0)), "creep"

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
                out["progress"], out["progress_mode"] = self.progress(job)
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
 small{color:#777} a{color:#8ac} .mode{color:#777;font-size:.85em}
 /* A time/eta/creep bar is an estimate, not a measurement. Hatching it keeps
    that visible at a glance so an estimated bar is never read as a counted one. */
 .est>div{background:repeating-linear-gradient(90deg,#8ac 0 6px,#4a6a86 6px 12px)}
</style>
<h1>progress <small id="ts"></small> <small id="filter"></small></h1>
<table><thead><tr><th>job</th><th>session</th><th>state</th><th>progress</th>
<th>eta</th><th>counters</th><th>detail</th></tr></thead>
<tbody id="rows"></tbody></table>
<h1 style="margin-top:2em">history <small>last runs per job · trend</small></h1>
<table><thead><tr><th>job</th><th>runs</th><th>durations</th><th>median</th>
<th>trend</th></tr></thead><tbody id="hist"></tbody></table>
<script>
function esc(s){const d=document.createElement("span");d.textContent=s==null?"":String(s);return d.innerHTML}
function dur(s){if(s==null)return"";s=Math.round(s);
 if(s<60)return s+"s";if(s<3600)return Math.floor(s/60)+"m"+String(s%60).padStart(2,"0")+"s";
 return Math.floor(s/3600)+"h"+String(Math.floor(s%3600/60)).padStart(2,"0")+"m"}
function spark(secs){const m=Math.max(...secs);
 return secs.map(s=>`<span style="display:inline-block;width:6px;margin-right:1px;`+
  `background:#8ac;height:${Math.max(2,Math.round(14*s/m))}px" title="${dur(s)}"></span>`).join("")}
// ?session=<id> narrows the page to one Claude Code session. The filter is
// applied by the daemon, not here, so the page and the status line ask the
// same question and cannot drift apart.
const Q=new URLSearchParams(location.search);
const SESSION=Q.get("session");
// The daemon now returns live work only unless asked otherwise, so the page
// carries the toggle rather than hiding finished rows with no way back.
const STATE=Q.get("state");
function qs(over){const p=new URLSearchParams();
 if(SESSION)p.set("session",SESSION);
 const s=over===undefined?STATE:over; if(s)p.set("state",s);
 const q=p.toString(); return q?"?"+q:"";}
function sessCell(j){
 if(!j.session)return "\u2014";
 const label=esc(j.session_name||j.session.slice(0,8));
 if(SESSION)return label;
 const p=new URLSearchParams();p.set("session",j.session);if(STATE)p.set("state",STATE);
 return `<a href="?${p.toString()}">${label}</a>`;
}
async function tick(){try{
 const r=await fetch("/jobs"+qs());
 const d=await r.json();
 document.getElementById("ts").textContent=d.now;
 const bits=[];
 if(SESSION){const p2=new URLSearchParams();if(STATE)p2.set("state",STATE);
  const href=p2.toString()?"?"+p2.toString():"?";
  bits.push(`session ${esc(SESSION.slice(0,8))} <a href="${href}">\u2715</a>`);}
 bits.push(STATE==="all"
  ?`showing all <a href="${qs(null)}">live only</a>`
  :`live only <a href="${qs("all")}">show all</a>`);
 document.getElementById("filter").innerHTML="\u00b7 "+bits.join(" \u00b7 ");
 document.getElementById("rows").innerHTML=d.jobs.map(j=>{
  const p=j.progress;
  const est=j.progress_mode&&j.progress_mode!=="items"&&j.progress_mode!=="done";
  let bar;
  if(p==null){bar=j.done;}
  else{
   const pct=Math.round(100*p);
   const tail=j.progress_mode==="items"?`${j.done}/${j.total}`
    :`${pct}% <span class="mode">${esc(j.progress_mode)}</span>`;
   bar=`<div class="bar${est?" est":""}"><div style="width:${pct}%"></div></div>${tail}`;
  }
  const c=j.counters?Object.entries(j.counters).map(([k,v])=>k+"="+v).join(" "):"";
  const det=esc(j.detail||j.error||"")+(j.tail?` <details><summary>output</summary><pre>${esc(j.tail)}</pre></details>`:"");
  return `<tr class="${j.state}"><td>${esc(j.name)}</td><td>${sessCell(j)}</td>`+
   `<td>${j.state}</td>`+
   `<td>${bar}</td><td>${dur(j.eta_seconds)}</td><td>${esc(c)}</td>`+
   `<td>${det}</td></tr>`}).join("");
 const h=await (await fetch("/history")).json();
 document.getElementById("hist").innerHTML=h.names.map(n=>{
  const t=n.trend=="stable"?"":`<span class="${n.trend=='slowing'?'failed':'running'}">`+
   `${n.trend} ${n.trend_pct>0?"+":""}${n.trend_pct}%</span>`;
  return `<tr><td>${esc(n.name)}</td><td>${n.runs}</td><td>${spark(n.seconds)}</td>`+
   `<td>${dur(n.median)}</td><td>${t}</td></tr>`}).join("");
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
                rows = tracker.snapshot()
                q = urllib.parse.parse_qs(path.query)

                want = (q.get("session") or [None])[0]
                if want:
                    # Exact match only. A job with no session (cron, bare shell)
                    # is deliberately excluded: a per-session view that quietly
                    # included machine-wide work would be worse than useless.
                    rows = [r for r in rows if r.get("session") == want]

                # state: absent -> live work only. A channel you glance at
                # should answer "what is happening now"; finished rows are
                # history and are one ?state=all away. Explicit states may be
                # comma-separated (?state=done,failed).
                state_q = (q.get("state") or [None])[0]
                if state_q != "all":
                    if state_q:
                        wanted = [s.strip() for s in state_q.split(",") if s.strip()]
                        rows = [r for r in rows if r.get("state") in wanted]
                    else:
                        # Live default: running work, plus anything that finished
                        # within the linger window so a job is actually seen
                        # reaching 100% instead of blinking out of existence.
                        linger = _linger_seconds()
                        now_dt = datetime.now(timezone.utc)

                        def _live(r: dict) -> bool:
                            if r.get("state") in LIVE_STATES:
                                return True
                            ts = _parse_ts(r.get("finished_at"))
                            return ts is not None and \
                                (now_dt - ts).total_seconds() <= linger

                        rows = [r for r in rows if _live(r)]

                self._json({"now": _now(), "jobs": rows})
            elif path.path == "/forecast":
                name = urllib.parse.parse_qs(path.query).get("name", [""])[0]
                self._json({"text": forecast_text(tracker.history, name)})
            elif path.path == "/history":
                self._json({"names": history_summary(tracker.history)})
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
                 project: str | None = None, expect_seconds: float | None = None,
                 ping_timeout: float | None = None):
        self.name, self.total, self.kind = name, total, kind
        self.source, self.detail = source, detail
        self.project = project or os.path.basename(os.getcwd())
        # Time-based work: pass expect_seconds when the job knows roughly how
        # long it should take but cannot count items (a download, a remote
        # build). Leave both total and expect_seconds unset and the bar falls
        # back to this job's own history, then to an open-ended creep.
        self.expect_seconds = expect_seconds
        # Watchdog: if the producer goes quiet for longer than this, the job is
        # declared stopped. Distinct from `stalled` (a learned, advisory guess
        # that resolves itself) and from `orphaned` (the pid is provably gone).
        # This is for producers whose pid says nothing useful — a remote job, a
        # shell that forks, anything polled rather than owned.
        self.ping_timeout = ping_timeout
        self.session, self.session_name, self.agent = session_identity()
        self.uid = uuid.uuid4().hex
        self.done = 0
        self.tail: str | None = None    # last output lines, shown on the page
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
            "expect_seconds": self.expect_seconds,
            "ping_timeout": self.ping_timeout,
            "session": self.session, "session_name": self.session_name,
            "agent": self.agent,
            "detail": self.detail, "tail": self.tail,
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
    # Deliberate surface: `list` is asked for, so it shows everything. Only the
    # ambient surfaces (page, status line) default to live work.
    data = _get_json("/jobs?state=all")
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
    from collections import deque
    tail: deque[str] = deque(maxlen=30)
    with Job(a.name, total=a.total, kind=a.kind,
             detail=" ".join(a.cmd)[:120]) as j:
        # Tee the command's output: the terminal sees everything live, the
        # channel keeps the last lines so a failed row on the page shows WHY.
        proc = subprocess.Popen(a.cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True,
                                errors="replace")
        for line in proc.stdout:
            sys.stdout.write(line)
            tail.append(line.rstrip("\n"))
        rc = proc.wait()
        j.tail = "\n".join(tail)[-2000:]
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


# ── shell integration: start / step / finish ───────────────────────────────
# Any script that can run a command can be a producer. `start` registers the
# job and prints a token; the cross-invocation producer state (done, counters,
# step gaps) lives in a token file, so `step` needs no daemon round-trip to
# know where it is. Liveness anchors to the CALLING script's pid (getppid),
# not the short-lived CLI process — a dead script is orphaned correctly.

_GAPS_KEEP = 100


def _token_path(token: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", token):
        raise SystemExit(f"progress: malformed token '{token}'")
    return home() / "tokens" / f"{token}.json"


def _token_load(token: str) -> dict:
    path = _token_path(token)
    if not path.exists():
        raise SystemExit(f"progress: unknown token {token} (already finished,"
                         " or started under a different $PROGRESS_HOME)")
    return json.loads(path.read_text(encoding="utf-8"))

def _token_save(token: str, state: dict) -> None:
    path = _token_path(token)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    tmp.replace(path)


def _token_record(state: dict, status: str = "running",
                  error: str | None = None) -> dict:
    rec = {k: state.get(k) for k in
           ("uid", "name", "kind", "source", "project", "total", "done",
            "detail", "pid", "host",
            "expect_seconds", "ping_timeout",
            "session", "session_name", "agent")}
    rec["status"] = status
    rec["counters"] = state.get("counters") or None
    if status != "running":
        started = _parse_ts(state.get("started_at"))
        seconds = (datetime.now(timezone.utc) - started).total_seconds() \
            if started else None
        rec["error"] = error
        rec["seconds"] = seconds
        rec["per_item"] = (seconds / state["done"]) \
            if state.get("done") and seconds else None
        gaps = state.get("gaps") or []
        rec["p95_gap"] = _percentile(gaps, 0.95) if len(gaps) >= 5 else None
    return rec


def cmd_start(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="progress start")
    ap.add_argument("--name", required=True)
    ap.add_argument("--total", type=int)
    ap.add_argument("--seconds", type=float, dest="expect_seconds",
                    help="expected duration; fills the bar on time when there "
                         "is nothing to count")
    ap.add_argument("--timeout", type=float, dest="ping_timeout",
                    help="declare the job stopped after this many seconds "
                         "without a step or ping")
    ap.add_argument("--kind", default="local")
    ap.add_argument("--source")
    ap.add_argument("--detail")
    ap.add_argument("--pid", type=int,
                    help="liveness pid (default: the calling script)")
    a = ap.parse_args(argv)
    state = {
        "uid": uuid.uuid4().hex, "name": a.name, "kind": a.kind,
        "source": a.source, "project": os.path.basename(os.getcwd()),
        "total": a.total, "done": 0, "detail": a.detail,
        "expect_seconds": a.expect_seconds, "ping_timeout": a.ping_timeout,
        "session": session_identity()[0], "session_name": session_identity()[1],
        "agent": session_identity()[2],
        "counters": {}, "gaps": [], "last_step": None,
        "last_post": 0.0, "started_at": _now(),
        "pid": a.pid or os.getppid(), "host": os.uname().nodename,
    }
    _token_save(state["uid"], state)
    if ensure_daemon():
        _post_job(_token_record(state))
    else:
        print(f"progress: daemon unreachable — '{a.name}' untracked",
              file=sys.stderr)
    print(state["uid"])
    return 0


def cmd_step(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="progress step")
    ap.add_argument("token")
    ap.add_argument("-n", type=int, default=1, help="items completed (default 1)")
    ap.add_argument("--done", type=int, help="set the absolute count instead")
    ap.add_argument("--total", type=int, help="set/adjust the total")
    ap.add_argument("--detail")
    ap.add_argument("--count", action="append", default=[],
                    metavar="KEY=N", help="categorical counter, repeatable")
    a = ap.parse_args(argv)
    state = _token_load(a.token)
    now = time.time()
    if state.get("last_step") is not None:
        state.setdefault("gaps", []).append(now - state["last_step"])
        state["gaps"] = state["gaps"][-_GAPS_KEEP:]
    state["last_step"] = now
    state["done"] = a.done if a.done is not None else state.get("done", 0) + a.n
    if a.total is not None:
        state["total"] = a.total
    if a.detail is not None:
        state["detail"] = a.detail
    for kv in a.count:
        k, _, v = kv.partition("=")
        state.setdefault("counters", {})
        state["counters"][k] = state["counters"].get(k, 0) + int(v or 1)
    # Same throttle discipline as the library: the token remembers the last
    # POST, so a tight shell loop stays a trickle of requests.
    if a.total is not None or now - state.get("last_post", 0) >= FLUSH_EVERY_SECONDS:
        if _post_job(_token_record(state)):
            state["last_post"] = now
    _token_save(state["uid"], state)
    return 0


def cmd_ping(argv: list[str]) -> int:
    """Heartbeat, with optional overrides.

    `step` advances a count and is throttled; `ping` says "still alive" and
    always POSTs immediately, because a heartbeat a throttle might swallow is
    not a heartbeat. Use it for time-based work with nothing to count, and to
    correct a job's shape mid-run (--total/--seconds/--timeout).
    """
    import argparse
    ap = argparse.ArgumentParser(prog="progress ping")
    ap.add_argument("token")
    ap.add_argument("-n", type=int, default=0,
                    help="items completed since the last ping (default 0)")
    ap.add_argument("--done", type=int, help="set the absolute count instead")
    ap.add_argument("--total", type=int, help="override the total")
    ap.add_argument("--seconds", type=float, dest="expect_seconds",
                    help="override the expected duration")
    ap.add_argument("--timeout", type=float, dest="ping_timeout",
                    help="override the no-ping-means-stopped window")
    ap.add_argument("--detail")
    a = ap.parse_args(argv)

    state = _token_load(a.token)
    now = time.time()
    if a.done is not None:
        state["done"] = a.done
    elif a.n:
        state["done"] = state.get("done", 0) + a.n
    for key, val in (("total", a.total), ("expect_seconds", a.expect_seconds),
                     ("ping_timeout", a.ping_timeout), ("detail", a.detail)):
        if val is not None:
            state[key] = val
    if a.n or a.done is not None:
        state["last_step"] = now
    if _post_job(_token_record(state)):     # never throttled
        state["last_post"] = now
    _token_save(state["uid"], state)
    return 0


def cmd_finish(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="progress finish")
    ap.add_argument("token")
    ap.add_argument("--fail", metavar="ERROR",
                    help="finish as failed with this error")
    ap.add_argument("--cancel", action="store_true")
    a = ap.parse_args(argv)
    state = _token_load(a.token)
    status = "failed" if a.fail else "cancelled" if a.cancel else "done"
    ensure_daemon()
    _post_job(_token_record(state, status=status, error=a.fail))
    _token_path(a.token).unlink(missing_ok=True)
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
    if verb == "start":
        return cmd_start(rest)
    if verb == "step":
        return cmd_step(rest)
    if verb == "ping":
        return cmd_ping(rest)
    if verb == "finish":
        return cmd_finish(rest)
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
