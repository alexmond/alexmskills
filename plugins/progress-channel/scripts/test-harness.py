#!/usr/bin/env python3
"""progress-channel harness — store, lifecycle, learning, liveness, CLI.

Runs against a throwaway store via $PROGRESS_DB; never touches the real
channel. Exit 0 all green, 1 otherwise.
"""
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
TMP = Path(tempfile.mkdtemp(prefix="progress-harness-"))
DB = TMP / "jobs.db"
os.environ["PROGRESS_DB"] = str(DB)

spec = importlib.util.spec_from_file_location("progress", HERE / "progress.py")
progress = importlib.util.module_from_spec(spec)
spec.loader.exec_module(progress)

PASS, FAIL = 0, []


def check(name, cond, note=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL.append(name)
        print(f"FAIL  {name}  {note}")


def row(name, **where):
    conn = progress.connect()
    q = "SELECT * FROM job WHERE name=?"
    args = [name]
    for k, v in where.items():
        q += f" AND {k}=?"; args.append(v)
    r = conn.execute(q + " ORDER BY id DESC", args).fetchone()
    conn.close()
    return r


# 1-3 · happy path -----------------------------------------------------------
with progress.Job("t-happy", total=120) as j:
    for i in range(120):
        j.step(detail=f"item-{i}", ok=1)
r = row("t-happy")
check("happy: status done", r["status"] == "done")
check("happy: done==total", r["done"] == 120 and r["total"] == 120)
check("happy: counters json", json.loads(r["counters"]) == {"ok": 120})

# 4 · crash records a failure ------------------------------------------------
try:
    with progress.Job("t-crash", total=10) as j:
        j.step()
        raise ValueError("boom")
except ValueError:
    pass
r = row("t-crash")
check("crash: status failed + error", r["status"] == "failed"
      and "ValueError" in (r["error"] or ""))

# 5 · throttled flush: mid-run row lags, exit flush lands everything ---------
flushes = {"n": 0}
orig = progress.Job._flush
def counting_flush(self, *a, **kw):
    flushes["n"] += 1
    return orig(self, *a, **kw)
progress.Job._flush = counting_flush
with progress.Job("t-throttle", total=1000) as j:
    for _ in range(1000):
        j.step()
progress.Job._flush = orig
check("throttle: flushes far below steps", 0 < flushes["n"] <= 30,
      f"flushes={flushes['n']}")
check("throttle: final flush lands full count", row("t-throttle")["done"] == 1000)

# 6-7 · history: shape key + retention cap -----------------------------------
for i in range(25):
    with progress.Job("t-hist", total=100) as j:
        j.done = 100
conn = progress.connect()
n = conn.execute("SELECT COUNT(*) FROM job_history WHERE name='t-hist'"
                 " AND total_bucket=3").fetchone()[0]
check("history: capped per shape key", n == progress.HISTORY_KEEP, f"n={n}")
with progress.Job("t-hist", total=100000) as j:  # different magnitude
    j.done = 100000
buckets = {r[0] for r in conn.execute(
    "SELECT DISTINCT total_bucket FROM job_history WHERE name='t-hist'")}
check("history: magnitude change = new shape key", buckets == {3, 6},
      f"buckets={buckets}")
conn.close()

# 8 · forecast ---------------------------------------------------------------
check("forecast: from history", "run(s)" in progress.forecast(
    progress.connect(), "t-hist"))
check("forecast: honest on first run", "no history" in progress.forecast(
    progress.connect(), "t-never-ran"))

# 9 · ETA cutover: past the threshold the current rate dominates -------------
conn = progress.connect()
conn.execute("INSERT INTO job_history (name, kind, total_bucket, seconds,"
             " per_item, status, finished_at) VALUES"
             " ('t-eta','local',3, 1000, 10.0, 'done', '2026-01-01T00:00:00Z')")
conn.close()
j = progress.Job("t-eta", total=100)
with j:
    j.done = 50                      # 50% > 10% cutover -> current rate only
    j._t0 = time.monotonic() - 5.0   # observed: 0.1 s/item vs history 10 s/item
    eta = progress._parse_ts(j._eta_at())
    left = (eta - datetime.now(timezone.utc)).total_seconds()
check("eta: current rate wins past cutover", 0 < left < 60, f"left={left}")

# 10 · orphan: dead-pid running row adjudicated by the next run --------------
conn = progress.connect()
conn.execute("INSERT INTO job (name, status, pid, host, updated_at) VALUES"
             " ('t-orphan','running', 999999999, ?, ?)",
             (os.uname().nodename, progress._now()))
conn.close()
with progress.Job("t-orphan") as j:
    pass
r = row("t-orphan", status="orphaned")
check("orphan: dead running row marked", r is not None)

# 11 · classify: orphaned + stalled vs healthy -------------------------------
conn = progress.connect()
conn.execute("INSERT INTO job (name, status, pid, host, updated_at) VALUES"
             " ('t-class','running', 999999999, ?, ?)",
             (os.uname().nodename, progress._now()))
r = conn.execute("SELECT * FROM job WHERE name='t-class'").fetchone()
check("classify: dead pid -> orphaned", progress.classify(conn, r) == "orphaned")
# stalled: own pid (alive) but silent >> learned p95 gap
conn.execute("INSERT INTO job_history (name, kind, total_bucket, p95_gap,"
             " status, finished_at) VALUES ('t-stall','local',0, 1.0,"
             " 'done', '2026-01-01T00:00:00Z')")
old = (datetime.now(timezone.utc) - timedelta(seconds=120)
       ).strftime("%Y-%m-%dT%H:%M:%SZ")
conn.execute("INSERT INTO job (name, status, pid, host, updated_at) VALUES"
             " ('t-stall','running', ?, ?, ?)",
             (os.getpid(), os.uname().nodename, old))
r = conn.execute("SELECT * FROM job WHERE name='t-stall'").fetchone()
check("classify: silent past learned gap -> stalled",
      progress.classify(conn, r) == "stalled")
# no history + alive pid: silence is NOT called a stall (always-slow jobs)
conn.execute("INSERT INTO job (name, status, pid, host, updated_at) VALUES"
             " ('t-slow','running', ?, ?, ?)",
             (os.getpid(), os.uname().nodename, old))
r = conn.execute("SELECT * FROM job WHERE name='t-slow'").fetchone()
check("classify: no history -> still running", progress.classify(conn, r) == "running")
conn.close()

# 12 · prune -----------------------------------------------------------------
conn = progress.connect()
conn.execute("INSERT INTO job (name, status, finished_at, updated_at) VALUES"
             " ('t-old','done', '2020-01-01T00:00:00Z', '2020-01-01T00:00:00Z')")
n = progress.prune(conn, days=7)
check("prune: drops old finished rows", n >= 1
      and conn.execute("SELECT COUNT(*) FROM job WHERE name='t-old'")
      .fetchone()[0] == 0)
check("prune: keeps running rows", conn.execute(
    "SELECT COUNT(*) FROM job WHERE name='t-stall'").fetchone()[0] == 1)
conn.close()

# 13 · CLI run wrapper -------------------------------------------------------
env = dict(os.environ)
rc = subprocess.run([sys.executable, str(HERE / "progress.py"), "run",
                     "--name", "t-cli-ok", "--", "true"], env=env).returncode
check("cli run: success -> done", rc == 0 and row("t-cli-ok")["status"] == "done")
rc = subprocess.run([sys.executable, str(HERE / "progress.py"), "run",
                     "--name", "t-cli-bad", "--", "false"], env=env,
                    capture_output=True).returncode
check("cli run: failure -> failed", rc != 0
      and row("t-cli-bad")["status"] == "failed")

# 14 · CLI list --------------------------------------------------------------
out = subprocess.run([sys.executable, str(HERE / "progress.py"), "list",
                      "--all"], env=env, capture_output=True, text=True).stdout
check("cli list: renders rows", "t-happy" in out and "✓" in out)

# 15 · mirror: poll-driven external job + lease refusal ----------------------
state = TMP / "poll-state"
state.write_text("5 10\n")
poll = f"cat {state}"
rc = subprocess.run(
    [sys.executable, str(HERE / "progress.py"), "mirror", "--name", "t-ext",
     "--source", "queue-a", "--poll-cmd", f"echo idle # {poll}",
     "--interval", "0.05", "--idle-after", "1"], env=env,
    capture_output=True, text=True).returncode
check("mirror: idle poll -> clean exit", rc == 0
      and row("t-ext")["status"] == "done")
# lease: plant a live running row for the source, second mirror must refuse
conn = progress.connect()
conn.execute("INSERT INTO job (name, kind, source, status, pid, host,"
             " updated_at) VALUES ('t-ext2','external','queue-b','running',"
             " ?, ?, ?)", (os.getpid(), os.uname().nodename, progress._now()))
conn.close()
p = subprocess.run(
    [sys.executable, str(HERE / "progress.py"), "mirror", "--name", "t-ext2",
     "--source", "queue-b", "--poll-cmd", "echo idle", "--interval", "0.05"],
    env=env, capture_output=True, text=True)
check("mirror: live lease refused", p.returncode == 3
      and "refusing" in p.stderr)

# 16 · concurrent writers don't error (busy_timeout) -------------------------
def worker(i):
    return subprocess.Popen(
        [sys.executable, "-c",
         f"import importlib.util; s=importlib.util.spec_from_file_location"
         f"('p', r'{HERE / 'progress.py'}'); p=importlib.util.module_from_spec(s);"
         f" s.loader.exec_module(p)\n"
         f"with p.Job('t-conc-{i}', total=200) as j:\n"
         f"    for _ in range(200): j.step()"], env=env)
procs = [worker(i) for i in range(4)]
rcs = [pr.wait() for pr in procs]
check("concurrency: 4 parallel writers all clean", all(rc == 0 for rc in rcs),
      f"rcs={rcs}")

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("failed:", ", ".join(FAIL))
sys.exit(1 if FAIL else 0)
