#!/usr/bin/env python3
"""progress-channel — one visible channel for every long-running process.

Library:  from progress import Job
    with Job('video integrity', total=10453) as j:
        for item in items:
            j.step(detail=item, ok=1)

CLI:      python3 progress.py list|watch|forecast|run|mirror|prune

Store: a dedicated SQLite file (WAL) at ~/.claude/progress/jobs.db —
deliberately NOT shared with any application's own store (a sweep holding a
write transaction between commits deadlocks a shared file; WAL permits one
writer). Override with $PROGRESS_DB (tests) or Job(db=...).

Design constraints carried from the reference implementation and the #36
review: the job is a context manager (a crash records a failure, never a
forever-running row); step() flushes on a throttle, not per item; duration
history is keyed by (name, kind, total-bucket) and capped; ETA cuts over
from history to the current run's own rate as progress accumulates; the
viewer derives liveness (orphaned/stalled) instead of trusting `running`.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import statistics
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Tunables. Constants, not config: the channel must behave identically for
# every producer or the view stops being trustworthy.
FLUSH_EVERY_STEPS = 50
FLUSH_EVERY_SECONDS = 1.0
HISTORY_KEEP = 20            # runs kept per (name, kind, total_bucket)
PRUNE_FINISHED_DAYS = 7      # finished job rows older than this are dropped
ETA_CUTOVER_FRACTION = 0.10  # current-run rate fully trusted past this progress
STALL_GAP_FACTOR = 3.0       # stalled when silent > factor * learned p95 gap
STALL_GAP_FLOOR = 30.0       # ... but never call a gap under this a stall

SCHEMA = """
CREATE TABLE IF NOT EXISTS job (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  kind        TEXT NOT NULL DEFAULT 'local',
  source      TEXT,
  project     TEXT,
  total       INTEGER,
  done        INTEGER NOT NULL DEFAULT 0,
  status      TEXT NOT NULL DEFAULT 'running',
  detail      TEXT,
  counters    TEXT,
  eta_at      TEXT,
  pid         INTEGER,
  host        TEXT,
  started_at  TEXT,
  updated_at  TEXT,
  finished_at TEXT,
  error       TEXT
);
CREATE INDEX IF NOT EXISTS job_status_idx ON job(status, updated_at);
CREATE TABLE IF NOT EXISTS job_history (
  name         TEXT NOT NULL,
  kind         TEXT,
  total_bucket INTEGER,
  total        INTEGER,
  done         INTEGER,
  seconds      REAL,
  per_item     REAL,
  p95_gap      REAL,
  status       TEXT,
  host         TEXT,
  finished_at  TEXT
);
CREATE INDEX IF NOT EXISTS job_history_name_idx ON job_history(name, finished_at);
"""


def db_path() -> Path:
    env = os.environ.get("PROGRESS_DB")
    if env:
        return Path(env)
    return Path.home() / ".claude" / "progress" / "jobs.db"


def connect(db: Path | None = None) -> sqlite3.Connection:
    path = Path(db) if db else db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(SCHEMA)
    return conn


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


class Job:
    """Context-managed progress row. Exiting on an exception records a
    failure; only SIGKILL-class deaths leave a running row, and the viewer
    catches those by pid liveness."""

    def __init__(self, name: str, total: int | None = None, kind: str = "local",
                 source: str | None = None, detail: str | None = None,
                 project: str | None = None, db: Path | None = None):
        self.name, self.total, self.kind = name, total, kind
        self.source, self.detail = source, detail
        self.project = project or os.path.basename(os.getcwd())
        self._db = db
        self.done = 0
        self.counters: dict[str, int] = {}
        self.id: int | None = None
        self._steps_since_flush = 0
        self._last_flush = 0.0
        self._last_step: float | None = None
        self._gaps: list[float] = []
        self._t0 = 0.0
        self._hist_per_item: float | None = None

    # -- lifecycle ---------------------------------------------------------
    def __enter__(self) -> "Job":
        self.conn = connect(self._db)
        self._mark_orphans()
        prune(self.conn, days=PRUNE_FINISHED_DAYS)
        self._hist_per_item = _hist_median_per_item(
            self.conn, self.name, self.kind, total_bucket(self.total))
        cur = self.conn.execute(
            "INSERT INTO job (name, kind, source, project, total, detail,"
            " pid, host, status, started_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?, 'running', ?, ?)",
            (self.name, self.kind, self.source, self.project, self.total,
             self.detail, os.getpid(), os.uname().nodename, _now(), _now()))
        self.id = cur.lastrowid
        self._t0 = time.monotonic()
        self._last_flush = self._t0
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        status = "failed" if exc_type else "done"
        error = f"{exc_type.__name__}: {exc}"[:500] if exc_type else None
        seconds = time.monotonic() - self._t0
        self._flush(final=True, status=status, error=error, seconds=seconds)
        self._write_history(status, seconds)
        self.conn.close()
        return False  # never swallow the exception

    def _mark_orphans(self) -> None:
        """A new run of NAME adjudicates its dead predecessors — a running
        row whose pid is gone on this host was killed too hard for __exit__."""
        host = os.uname().nodename
        for row in self.conn.execute(
                "SELECT id, pid, host FROM job WHERE name=? AND status='running'",
                (self.name,)):
            if row["host"] == host and not pid_alive(row["pid"]):
                self.conn.execute(
                    "UPDATE job SET status='orphaned', finished_at=?,"
                    " error='no __exit__: process died' WHERE id=?",
                    (_now(), row["id"]))

    # -- progress ----------------------------------------------------------
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

    def _eta_at(self) -> str | None:
        """Pre-cutover the history median predicts; as the run's own evidence
        accumulates its observed rate takes over (blend by progress)."""
        if not self.total or self.done <= 0:
            return None
        elapsed = time.monotonic() - self._t0
        current = elapsed / self.done
        if self._hist_per_item is not None:
            w = min(1.0, (self.done / self.total) / ETA_CUTOVER_FRACTION)
            rate = w * current + (1 - w) * self._hist_per_item
        else:
            rate = current
        remaining = max(0, self.total - self.done)
        eta = datetime.now(timezone.utc) + timedelta(seconds=remaining * rate)
        return eta.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _flush(self, final: bool = False, status: str | None = None,
               error: str | None = None, seconds: float | None = None) -> None:
        sets = ["done=?", "detail=?", "counters=?", "updated_at=?", "eta_at=?",
                "total=?"]
        args: list = [self.done, self.detail,
                      json.dumps(self.counters) if self.counters else None,
                      _now(), None if final else self._eta_at(), self.total]
        if final:
            sets += ["status=?", "finished_at=?", "error=?"]
            args += [status, _now(), error]
        args.append(self.id)
        self.conn.execute(f"UPDATE job SET {', '.join(sets)} WHERE id=?", args)
        self._steps_since_flush = 0
        self._last_flush = time.monotonic()

    def _write_history(self, status: str, seconds: float) -> None:
        per_item = (seconds / self.done) if self.done else None
        p95 = _percentile(self._gaps, 0.95) if len(self._gaps) >= 5 else None
        bucket = total_bucket(self.total)
        self.conn.execute(
            "INSERT INTO job_history (name, kind, total_bucket, total, done,"
            " seconds, per_item, p95_gap, status, host, finished_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (self.name, self.kind, bucket, self.total, self.done, seconds,
             per_item, p95, status, os.uname().nodename, _now()))
        # retention: an ETA input, not an archive
        self.conn.execute(
            "DELETE FROM job_history WHERE name=? AND kind=? AND total_bucket=?"
            " AND rowid NOT IN (SELECT rowid FROM job_history WHERE name=?"
            "  AND kind=? AND total_bucket=? ORDER BY finished_at DESC LIMIT ?)",
            (self.name, self.kind, bucket,
             self.name, self.kind, bucket, HISTORY_KEEP))


# -- history / forecast ----------------------------------------------------

def _hist_rows(conn: sqlite3.Connection, name: str, kind: str | None = None,
               bucket: int | None = None) -> list[sqlite3.Row]:
    q = "SELECT * FROM job_history WHERE name=? AND status='done'"
    args: list = [name]
    if kind is not None:
        q += " AND kind=?"; args.append(kind)
    if bucket is not None:
        q += " AND total_bucket=?"; args.append(bucket)
    q += " ORDER BY finished_at DESC LIMIT ?"
    args.append(HISTORY_KEEP)
    return list(conn.execute(q, args))


def _hist_median_per_item(conn, name, kind, bucket) -> float | None:
    vals = [r["per_item"] for r in _hist_rows(conn, name, kind, bucket)
            if r["per_item"]]
    return statistics.median(vals) if vals else None


def _hist_p95_gap(conn, name) -> float | None:
    vals = [r["p95_gap"] for r in _hist_rows(conn, name) if r["p95_gap"]]
    return statistics.median(vals) if vals else None


def forecast(conn: sqlite3.Connection, name: str) -> str:
    rows = _hist_rows(conn, name)
    if not rows:
        return f"{name}: no history — first run has no estimate."
    secs = [r["seconds"] for r in rows if r["seconds"]]
    lo, hi = _percentile(secs, 0.25), _percentile(secs, 0.75)
    return (f"{name}: {_fmt_dur(lo)}–{_fmt_dur(hi)} over the last "
            f"{len(secs)} successful run(s) (median {_fmt_dur(statistics.median(secs))}).")


# -- viewer-side liveness --------------------------------------------------

def classify(conn: sqlite3.Connection, row: sqlite3.Row,
             now: datetime | None = None) -> str:
    """The view never trusts `running` at face value — that is how counters
    lie. Liveness is derived from pid and the job's own learned cadence."""
    if row["status"] != "running":
        return row["status"]
    host = os.uname().nodename
    if row["host"] == host and not pid_alive(row["pid"]):
        return "orphaned"
    now = now or datetime.now(timezone.utc)
    updated = _parse_ts(row["updated_at"])
    if updated is not None:
        silent = (now - updated).total_seconds()
        p95 = _hist_p95_gap(conn, row["name"])
        if p95 is not None and silent > max(STALL_GAP_FACTOR * p95,
                                            STALL_GAP_FLOOR):
            return "stalled"
    return "running"


# -- CLI -------------------------------------------------------------------

def _fmt_dur(s: float | None) -> str:
    if s is None:
        return "?"
    s = int(s)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


def _fmt_row(conn, row) -> str:
    state = classify(conn, row)
    frac = (f"{row['done']}/{row['total']}" if row["total"]
            else str(row["done"]))
    eta = ""
    if state == "running" and row["eta_at"]:
        left = (_parse_ts(row["eta_at"]) - datetime.now(timezone.utc)).total_seconds()
        eta = f" eta {_fmt_dur(left)}" if left > 0 else " eta now"
    counters = ""
    if row["counters"]:
        c = json.loads(row["counters"])
        counters = " " + " ".join(f"{k}={v}" for k, v in c.items())
    detail = f" · {row['detail']}" if row["detail"] else ""
    mark = {"running": "▶", "done": "✓", "failed": "✗", "orphaned": "☠",
            "stalled": "⏸", "cancelled": "∅"}.get(state, "?")
    return (f"{mark} {row['name']:32.32} {state:9} {frac:>13}{eta}"
            f"{counters}{detail}")


def cmd_list(conn: sqlite3.Connection, show_all: bool = False) -> list[str]:
    q = "SELECT * FROM job"
    if not show_all:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)
                  ).strftime("%Y-%m-%dT%H:%M:%SZ")
        q += f" WHERE status='running' OR finished_at > '{cutoff}'"
    q += " ORDER BY (status='running') DESC, updated_at DESC LIMIT 40"
    lines = [_fmt_row(conn, r) for r in conn.execute(q)]
    return lines or ["(no jobs)"]


def cmd_watch(conn: sqlite3.Connection, interval: float) -> None:
    try:
        while True:
            lines = cmd_list(conn)
            sys.stdout.write("\x1b[2J\x1b[H")  # clear + home
            print(f"progress · {db_path()} · {_now()}  (ctrl-c to quit)\n")
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
    The running job row itself is the lease: a second mirror for the same
    source refuses to start while the first is alive."""
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

    conn = connect()
    for row in conn.execute(
            "SELECT * FROM job WHERE source=? AND status='running'", (a.source,)):
        if row["host"] == os.uname().nodename and pid_alive(row["pid"]):
            print(f"refusing: live watcher pid={row['pid']} already mirrors"
                  f" source '{a.source}' (job #{row['id']})", file=sys.stderr)
            conn.close()
            return 3
    conn.close()

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
                done = int(m.group(1))
                if m.group(2):
                    j.total = int(m.group(2))
                j.done = done
                if j.total and done >= j.total:
                    idle = a.idle_after
            j.step(0)  # heartbeat: updates updated_at without inflating done
            j._flush()
            if idle < a.idle_after:
                time.sleep(a.interval)
    return 0


def prune(conn: sqlite3.Connection, days: int = PRUNE_FINISHED_DAYS) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)
              ).strftime("%Y-%m-%dT%H:%M:%SZ")
    cur = conn.execute(
        "DELETE FROM job WHERE status != 'running' AND finished_at < ?",
        (cutoff,))
    return cur.rowcount


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    verb, rest = argv[0], argv[1:]
    if verb == "run":
        return cmd_run(rest)
    if verb == "mirror":
        return cmd_mirror(rest)
    conn = connect()
    try:
        if verb == "list":
            print("\n".join(cmd_list(conn, show_all="--all" in rest)))
            return 0
        if verb == "watch":
            interval = float(rest[rest.index("--interval") + 1]) \
                if "--interval" in rest else 2.0
            cmd_watch(conn, interval)
            return 0
        if verb == "forecast":
            if not rest:
                print("usage: progress forecast <name>", file=sys.stderr)
                return 2
            print(forecast(conn, rest[0]))
            return 0
        if verb == "prune":
            days = int(rest[rest.index("--days") + 1]) \
                if "--days" in rest else PRUNE_FINISHED_DAYS
            print(f"pruned {prune(conn, days)} finished row(s)")
            return 0
        print(f"unknown verb: {verb}", file=sys.stderr)
        return 2
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
