#!/usr/bin/env python3
"""progress-channel harness — daemon lifecycle, learning, liveness, CLI.

Spawns a real daemon on an ephemeral port with a throwaway $PROGRESS_HOME;
never touches the real channel. Exit 0 all green, 1 otherwise.
"""
import importlib.util
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
TMP = Path(tempfile.mkdtemp(prefix="progress-harness-"))
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    PORT = s.getsockname()[1]
os.environ["PROGRESS_HOME"] = str(TMP)
os.environ["PROGRESS_PORT"] = str(PORT)
os.environ["PROGRESS_SWEEP"] = "0.2"

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


def jobs(name=None):
    data = progress._get_json("/jobs") or {"jobs": []}
    rows = data["jobs"]
    return [j for j in rows if j.get("name") == name] if name else rows


def wait_for(pred, timeout=3.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return True
        time.sleep(0.1)
    return False


# 1 · auto-spawn: no daemon running, first Job brings one up ----------------
check("spawn: no daemon before first job",
      progress._get_json("/health", timeout=0.3) is None)
with progress.Job("t-happy", total=120) as j:
    for i in range(120):
        j.step(detail=f"item-{i}", ok=1)
check("spawn: first job auto-spawned the daemon",
      progress._get_json("/health") is not None)

# 2-3 · happy path -----------------------------------------------------------
r = jobs("t-happy")[0]
check("happy: state done, done==total",
      r["state"] == "done" and r["done"] == 120 and r["total"] == 120)
check("happy: categorical counters", r["counters"] == {"ok": 120})

# 4 · crash records a failure ------------------------------------------------
try:
    with progress.Job("t-crash", total=10) as j:
        j.step()
        raise ValueError("boom")
except ValueError:
    pass
r = jobs("t-crash")[0]
check("crash: failed + error", r["state"] == "failed"
      and "ValueError" in (r.get("error") or ""))

# 5 · throttle: 1000 steps, few POSTs ---------------------------------------
posts = {"n": 0}
orig_post = progress._post_job
def counting_post(rec, timeout=1.0):
    posts["n"] += 1
    return orig_post(rec, timeout)
progress._post_job = counting_post
with progress.Job("t-throttle", total=1000) as j:
    for _ in range(1000):
        j.step()
progress._post_job = orig_post
check("throttle: posts far below steps", 0 < posts["n"] <= 30,
      f"posts={posts['n']}")
check("throttle: final flush lands full count",
      jobs("t-throttle")[0]["done"] == 1000)

# 6 · SIGKILL producer -> daemon sweep marks orphaned ------------------------
code = (f"import importlib.util,os,time,signal;"
        f"s=importlib.util.spec_from_file_location('p', r'{HERE / 'progress.py'}');"
        f"p=importlib.util.module_from_spec(s); s.loader.exec_module(p)\n"
        f"j=p.Job('t-orphan', total=100)\n"
        f"j.__enter__(); j.step(5)\n"
        f"print('registered', flush=True)\n"
        f"time.sleep(30)")
proc = subprocess.Popen([sys.executable, "-c", code], env=dict(os.environ),
                        stdout=subprocess.PIPE, text=True)
proc.stdout.readline()  # wait until registered
proc.kill()             # SIGKILL: __exit__ never runs
proc.wait()
check("orphan: daemon sweep adjudicates dead pid",
      wait_for(lambda: jobs("t-orphan")
               and jobs("t-orphan")[0]["state"] == "orphaned"),
      f"state={jobs('t-orphan')}")

# 7-8 · history: shape key + cap + persistence -------------------------------
for i in range(25):
    with progress.Job("t-hist", total=100) as j:
        j.done = 100
with progress.Job("t-hist", total=100000) as j:  # different magnitude
    j.done = 100000
hist = progress.load_history()
n3 = [r for r in hist if r["name"] == "t-hist" and r["total_bucket"] == 3]
n6 = [r for r in hist if r["name"] == "t-hist" and r["total_bucket"] == 6]
check("history: persisted to jsonl + magnitude = new shape key",
      len(n3) == 26 - 1 and len(n6) == 1, f"n3={len(n3)} n6={len(n6)}")
check("history: compaction caps per shape key",
      len([r for r in progress.compact_history(hist)
           if r["name"] == "t-hist" and r["total_bucket"] == 3])
      == progress.HISTORY_KEEP)

# 9 · forecast ---------------------------------------------------------------
data = progress._get_json("/forecast?name=t-hist")
check("forecast: daemon serves band from history", "run(s)" in data["text"])
data = progress._get_json("/forecast?name=t-never-ran")
check("forecast: honest on first run", "no history" in data["text"])

# 10 · ETA cutover: current rate dominates past threshold --------------------
t = progress.Tracker()
t.history = [{"name": "t-eta", "kind": "local", "total_bucket": 3,
              "per_item": 10.0, "status": "done", "seconds": 1000,
              "finished_at": "2026-01-01T00:00:00Z"}]
started = (datetime.now(timezone.utc) - timedelta(seconds=5)
           ).strftime("%Y-%m-%dT%H:%M:%SZ")
eta = t.eta_seconds({"name": "t-eta", "kind": "local", "total": 100,
                     "done": 50, "started_at": started})
check("eta: current rate wins past cutover", eta is not None and eta < 60,
      f"eta={eta}")
eta_early = t.eta_seconds({"name": "t-eta", "kind": "local", "total": 100,
                           "done": 1, "started_at": started})
check("eta: history dominates early", eta_early is not None and eta_early > 500,
      f"eta={eta_early}")

# 11 · classify: stalled vs always-slow --------------------------------------
t.history.append({"name": "t-stall", "status": "done", "p95_gap": 1.0,
                  "kind": "local", "total_bucket": 0,
                  "finished_at": "2026-01-01T00:00:00Z"})
old = (datetime.now(timezone.utc) - timedelta(seconds=120)
       ).strftime("%Y-%m-%dT%H:%M:%SZ")
alive = {"status": "running", "pid": os.getpid(),
         "host": os.uname().nodename, "updated_at": old}
check("classify: silent past learned gap -> stalled",
      t.classify({**alive, "name": "t-stall"}) == "stalled")
check("classify: no history -> still running",
      t.classify({**alive, "name": "t-slow"}) == "running")
check("classify: dead pid -> orphaned",
      t.classify({**alive, "name": "t-stall", "pid": 999999999}) == "orphaned")

# 12 · CLI run wrapper -------------------------------------------------------
env = dict(os.environ)
rc = subprocess.run([sys.executable, str(HERE / "progress.py"), "run",
                     "--name", "t-cli-ok", "--", "true"], env=env).returncode
check("cli run: success -> done", rc == 0
      and jobs("t-cli-ok")[0]["state"] == "done")
rc = subprocess.run([sys.executable, str(HERE / "progress.py"), "run",
                     "--name", "t-cli-bad", "--", "false"], env=env,
                    capture_output=True).returncode
check("cli run: failure -> failed", rc != 0
      and jobs("t-cli-bad")[0]["state"] == "failed")

# 13 · CLI list --------------------------------------------------------------
out = subprocess.run([sys.executable, str(HERE / "progress.py"), "list"],
                     env=env, capture_output=True, text=True).stdout
check("cli list: renders rows", "t-happy" in out and "✓" in out)

# 14 · the page --------------------------------------------------------------
with urllib.request.urlopen(progress.base_url() + "/") as r:
    page = r.read().decode()
check("page: served html view", "<table" in page and "/jobs" in page)

# 15 · mirror: poll-driven external job + lease refusal ----------------------
rc = subprocess.run(
    [sys.executable, str(HERE / "progress.py"), "mirror", "--name", "t-ext",
     "--source", "queue-a", "--poll-cmd", "echo idle",
     "--interval", "0.05", "--idle-after", "1"], env=env,
    capture_output=True, text=True).returncode
check("mirror: idle poll -> clean exit", rc == 0
      and jobs("t-ext")[0]["state"] == "done")
# lease: a live running job for the source blocks a second mirror
blocker = subprocess.Popen(
    [sys.executable, "-c",
     f"import importlib.util,time;"
     f"s=importlib.util.spec_from_file_location('p', r'{HERE / 'progress.py'}');"
     f"p=importlib.util.module_from_spec(s); s.loader.exec_module(p)\n"
     f"with p.Job('t-ext2', kind='external', source='queue-b') as j:\n"
     f"    print('up', flush=True); time.sleep(10)"],
    env=env, stdout=subprocess.PIPE, text=True)
blocker.stdout.readline()
p = subprocess.run(
    [sys.executable, str(HERE / "progress.py"), "mirror", "--name", "t-ext2b",
     "--source", "queue-b", "--poll-cmd", "echo idle", "--interval", "0.05"],
    env=env, capture_output=True, text=True)
check("mirror: live lease refused", p.returncode == 3 and "refusing" in p.stderr)
blocker.send_signal(signal.SIGTERM)
blocker.wait()

# 16 · concurrent producers --------------------------------------------------
def worker(i):
    return subprocess.Popen(
        [sys.executable, "-c",
         f"import importlib.util;"
         f"s=importlib.util.spec_from_file_location('p', r'{HERE / 'progress.py'}');"
         f"p=importlib.util.module_from_spec(s); s.loader.exec_module(p)\n"
         f"with p.Job('t-conc-{i}', total=200) as j:\n"
         f"    for _ in range(200): j.step()"], env=env)
procs = [worker(i) for i in range(4)]
rcs = [pr.wait() for pr in procs]
check("concurrency: 4 parallel producers all clean",
      all(rc == 0 for rc in rcs)
      and all(jobs(f"t-conc-{i}")[0]["done"] == 200 for i in range(4)),
      f"rcs={rcs}")

# 17 · daemon restart: producer re-registers on next flush -------------------
health = progress._get_json("/health")
os.kill(health["pid"], signal.SIGTERM)
time.sleep(0.3)
progress._spawn_attempted = False       # allow one more spawn in this process
with progress.Job("t-revive", total=10) as j:
    for _ in range(10):
        j.step()
check("restart: fresh daemon, job re-registered",
      jobs("t-revive") and jobs("t-revive")[0]["done"] == 10)
check("restart: history survived the restart",
      "run(s)" in (progress._get_json("/forecast?name=t-hist") or {}).get("text", ""))

# 18 · degrade: unreachable + unspawnable daemon never breaks the job --------
bad_env_port = os.environ["PROGRESS_PORT"]
os.environ["PROGRESS_PORT"] = "1"       # can't bind a privileged port
progress._spawn_attempted = False
try:
    with progress.Job("t-degrade", total=3) as j:
        j.step(3)
    check("degrade: job runs untracked, no exception", True)
except Exception as e:
    check("degrade: job runs untracked, no exception", False, repr(e))
finally:
    os.environ["PROGRESS_PORT"] = bad_env_port

# cleanup --------------------------------------------------------------------
health = progress._get_json("/health")
if health:
    os.kill(health["pid"], signal.SIGTERM)

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("failed:", ", ".join(FAIL))
sys.exit(1 if FAIL else 0)
