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
    # state=all: these tests assert on finished/orphaned rows too. The bare
    # /jobs default is live-only, which is the *view* default, not the store.
    data = progress._get_json("/jobs?state=all") or {"jobs": []}
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

# 19-21 · shell trio: start / step / finish ----------------------------------
P = str(HERE / "progress.py")
tok = subprocess.run([sys.executable, P, "start", "--name", "t-shell",
                      "--total", "6"], env=env, capture_output=True,
                     text=True).stdout.strip()
check("shell: start prints a token", len(tok) == 32, f"tok={tok!r}")
for i in range(6):
    subprocess.run([sys.executable, P, "step", tok, "--count", "ok=1",
                    "--detail", f"f{i}"], env=env, check=True)
subprocess.run([sys.executable, P, "finish", tok], env=env, check=True)
r = jobs("t-shell")[0]
check("shell: steps accumulated, finished done",
      r["state"] == "done" and r["done"] == 6 and r["counters"] == {"ok": 6},
      f"r={r}")
check("shell: token file cleaned up",
      not (TMP / "tokens" / f"{tok}.json").exists())
check("shell: run landed in history",
      any(h["name"] == "t-shell" for h in progress.load_history()))

# 22 · shell trio: --fail ----------------------------------------------------
tok = subprocess.run([sys.executable, P, "start", "--name", "t-shell-bad"],
                     env=env, capture_output=True, text=True).stdout.strip()
subprocess.run([sys.executable, P, "step", tok], env=env, check=True)
subprocess.run([sys.executable, P, "finish", tok, "--fail", "disk full"],
               env=env, check=True)
r = jobs("t-shell-bad")[0]
check("shell: finish --fail -> failed + error",
      r["state"] == "failed" and r.get("error") == "disk full")

# 23 · shell trio: liveness anchors to the calling script --------------------
script = (f'T=$({sys.executable} "{P}" start --name t-shell-orphan --total 9);'
          f'{sys.executable} "{P}" step $T; echo up; sleep 30')
sh = subprocess.Popen(["bash", "-c", script], env=env,
                      stdout=subprocess.PIPE, text=True)
sh.stdout.readline()
sh.kill()   # SIGKILL the script: no finish ever runs
sh.wait()
check("shell: dead script swept as orphaned",
      wait_for(lambda: jobs("t-shell-orphan")
               and jobs("t-shell-orphan")[0]["state"] == "orphaned"),
      f"{jobs('t-shell-orphan')}")

# 24 · shell trio: unknown token fails loudly --------------------------------
p = subprocess.run([sys.executable, P, "step", "0" * 32], env=env,
                   capture_output=True, text=True)
check("shell: unknown token is a clear error", p.returncode != 0
      and "unknown token" in p.stderr)

# 25 · notify hook fires on finish -------------------------------------------
notify_out = TMP / "notify-out"
hook = TMP / "notify"
hook.write_text("#!/bin/sh\necho \"$PROGRESS_EVENT $PROGRESS_NAME"
                " $PROGRESS_ERROR\" >> " + str(notify_out) + "\n")
hook.chmod(0o755)
try:
    with progress.Job("t-notify") as j:
        raise ValueError("kaboom")
except ValueError:
    pass
check("notify: hook ran with event env",
      wait_for(lambda: notify_out.exists()
               and "failed t-notify ValueError: kaboom" in notify_out.read_text()),
      notify_out.read_text() if notify_out.exists() else "no file")

# 26 · trend detection --------------------------------------------------------
rows = [{"name": "t-trend", "kind": "local", "total_bucket": 2,
         "seconds": s, "status": "done", "finished_at": f"2026-01-0{i+1}T00:00:00Z"}
        for i, s in enumerate([100, 100, 100, 150, 160])]
label, pct = progress.trend(rows, "t-trend")
check("trend: slowing detected", label == "slowing" and pct > 25,
      f"{label} {pct}")
check("trend: stable on flat history",
      progress.trend(rows[:4][:3] + rows[:1], "t-trend")[0] == "stable")

# 27 · /history endpoint ------------------------------------------------------
h = progress._get_json("/history")
names = {n["name"] for n in h["names"]}
check("history endpoint: per-name digest with medians",
      "t-hist" in names and all("median" in n for n in h["names"]))

# 28 · run: output tail captured on failure ----------------------------------
rc = subprocess.run([sys.executable, P, "run", "--name", "t-tail", "--",
                     "sh", "-c", "echo out-line; echo err-line >&2; exit 3"],
                    env=env, capture_output=True, text=True).returncode
r = jobs("t-tail")[0]
check("run: failed row carries output tail", rc != 0
      and "out-line" in (r.get("tail") or "")
      and "err-line" in (r.get("tail") or ""), f"tail={r.get('tail')!r}")

# 29-30 · MCP shim ------------------------------------------------------------
mcp = subprocess.Popen([sys.executable, str(HERE / "progress_mcp.py")],
                       env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                       text=True)
def rpc(obj):
    mcp.stdin.write(json.dumps(obj) + "\n")
    mcp.stdin.flush()
    return json.loads(mcp.stdout.readline())
init = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
tools = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
names = {t["name"] for t in tools["result"]["tools"]}
check("mcp: initialize + full tool set",
      init["result"]["serverInfo"]["name"] == "progress-channel"
      and names == {"progress_list", "progress_forecast", "progress_start",
                    "progress_step", "progress_finish"})
listed = rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
              "params": {"name": "progress_list", "arguments": {}}})
fc = rpc({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
          "params": {"name": "progress_forecast",
                     "arguments": {"name": "t-hist"}}})
check("mcp: list + forecast answer through the daemon",
      "t-tail" in listed["result"]["content"][0]["text"]  # post-restart job
      and "run(s)" in fc["result"]["content"][0]["text"])
mcp.stdin.close()
mcp.wait()

# 31-33 · advisory hook -------------------------------------------------------
HOOK = str(HERE.parent / "hooks" / "suggest-progress.py")
def hook_out(tool_input):
    p = subprocess.run([sys.executable, HOOK], env=env,
                       input=json.dumps({"tool_name": "Bash",
                                         "tool_input": tool_input}),
                       capture_output=True, text=True)
    return p.stdout.strip()
out = hook_out({"command": "mvn -q verify"})
check("hook: long-runner gets a suggestion",
      "progress-channel" in out and "additionalContext" in out)
check("hook: short safe command stays silent",
      hook_out({"command": "git status"}) == "")
# learned: seed history for a shape the static list would never match
progress.append_history({"name": "perl slowthing.pl", "kind": "background",
                         "total_bucket": 0, "seconds": 120.0, "status": "done",
                         "finished_at": "2026-01-01T00:00:00Z"})
out = hook_out({"command": "perl slowthing.pl --all"})
check("hook: learned history triggers the suggestion",
      "tracked history" in out, out[:120])

# session identity, per-session query, agent attribution ----------------------
def _jobs(q=""):
    return (progress._get_json("/jobs" + q) or {"jobs": []})["jobs"]

os.environ["CLAUDE_CODE_SESSION_ID"] = "sess-AAA"
with progress.Job("sess A job", total=2) as ja:
    ja.step()
    os.environ["CLAUDE_CODE_SESSION_ID"] = "sess-BBB"
    os.environ["CLAUDE_CODE_AGENT"] = "explorer"
    with progress.Job("sess B job", total=2) as jb:
        jb.step()
        a_rows = _jobs("?session=sess-AAA")
        b_rows = _jobs("?session=sess-BBB")
        allrows = _jobs("?state=all")
        check("session: record carries the id from the environment",
              any(r.get("session") == "sess-AAA" for r in allrows))
        check("session: query returns only that session",
              [r["name"] for r in a_rows] == ["sess A job"], str(a_rows)[:120])
        check("session: the other session is not visible",
              all(r.get("session") == "sess-BBB" for r in b_rows))
        check("agent: subagent job is attributed",
              any(r.get("agent") == "explorer" for r in b_rows), str(b_rows)[:120])
        check("agent: main-loop job carries no agent",
              all(not r.get("agent") for r in a_rows))
os.environ.pop("CLAUDE_CODE_AGENT", None)
os.environ.pop("CLAUDE_CODE_SESSION_ID", None)

# progress modes ---------------------------------------------------------------
with progress.Job("mode items", total=4) as j:
    j.step(); j.step()
    j._flush()                      # steps are throttled; force the POST
    r = jobs("mode items")[0]
    check("progress: items mode is measured",
          r["progress_mode"] == "items" and abs(r["progress"] - 0.5) < 1e-6,
          str(r.get("progress")))

with progress.Job("mode time", expect_seconds=100) as j:
    r = jobs("mode time")[0]
    check("progress: declared duration gives time mode",
          r["progress_mode"] == "time" and 0 <= r["progress"] < 0.2, str(r.get("progress")))

with progress.Job("mode creep") as j:
    r = jobs("mode creep")[0]
    check("progress: nothing to measure gives creep",
          r["progress_mode"] == "creep" and r["progress"] < 0.1, str(r.get("progress")))

with progress.Job("mode eta") as j:      # first run seeds the history
    time.sleep(0.4)
with progress.Job("mode eta") as j:      # second run can estimate against it
    time.sleep(0.2)
    r = [x for x in jobs("mode eta") if x["state"] == "running"][0]
    check("progress: own history gives eta mode", r["progress_mode"] == "eta",
          str(r.get("progress_mode")))

# state filter + linger --------------------------------------------------------
with progress.Job("live one", total=2) as j:
    j.step()
    names = {r["name"] for r in _jobs()}
    check("state: bare /jobs returns live work", "live one" in names)
    # The whole suite runs in seconds, so every finished row is still inside the
    # linger window — "is an old row hidden" is not observable here. Assert the
    # invariant that produces that behaviour instead: any non-live row in the
    # bare view finished within the linger, and the bare view never exceeds all.
    import datetime as _dt
    _lin = progress._linger_seconds()
    _now = _dt.datetime.now(_dt.timezone.utc)
    _stale = [r["name"] for r in _jobs()
              if r["state"] not in progress.LIVE_STATES
              and (progress._parse_ts(r.get("finished_at")) is None
                   or (_now - progress._parse_ts(r["finished_at"])).total_seconds() > _lin)]
    check("state: bare /jobs carries no finished row past the linger",
          _stale == [], str(_stale)[:160])
    check("state: bare /jobs is a subset of ?state=all",
          names <= {r["name"] for r in _jobs("?state=all")})
    check("state: ?state=all still returns finished rows",
          "mode items" in {r["name"] for r in _jobs("?state=all")})
    check("state: explicit ?state=done selects only that",
          all(r["state"] == "done" for r in _jobs("?state=done")))

check("linger: a just-finished job is still in the live view",
      "live one" in {r["name"] for r in _jobs()})
check("linger: it is a finished row, not a running one",
      all(r["state"] != "running" for r in _jobs() if r["name"] == "live one"),
      str([r["state"] for r in _jobs() if r["name"] == "live one"]))

# ping heartbeat + watchdog ----------------------------------------------------
P = [sys.executable, str(HERE / "progress.py")]
tok = subprocess.run(P + ["start", "--name", "pinger", "--seconds", "60",
                          "--timeout", "1", "--pid", "1"],
                     capture_output=True, text=True).stdout.strip()
subprocess.run(P + ["ping", tok, "-n", "3"], capture_output=True)
r = jobs("pinger")[0]
check("ping: advances the count and posts immediately", r.get("done") == 3, str(r.get("done")))
check("ping: --timeout is recorded on the job", r.get("ping_timeout") == 1.0,
      str(r.get("ping_timeout")))
subprocess.run(P + ["ping", tok, "--total", "50", "--seconds", "5"], capture_output=True)
r = jobs("pinger")[0]
check("ping: overrides total and expected duration",
      r.get("total") == 50 and r.get("expect_seconds") == 5.0,
      f"total={r.get('total')} secs={r.get('expect_seconds')}")

check("watchdog: silence past --timeout marks the job stopped",
      wait_for(lambda: any(x.get("state") == "stopped"
                           for x in jobs("pinger")), timeout=8.0),
      str([x.get("state") for x in jobs("pinger")]))

# eta counts down -------------------------------------------------------------
# Regression: the rate used to be elapsed/done measured at *now*, so between
# two item completions it inflated every second and "time left" counted UP.
# total is large on purpose: with a small total the remaining estimate is only
# a few seconds, so a slow moment floors both samples at zero and the assertion
# becomes a coin flip. 100 items keeps the estimate far above the sample gap.
with progress.Job("eta countdown", total=100) as ej:
    # 1.1s, not 0.4s: _now() is second-resolution, so sub-second steps all share
    # a timestamp and the job has no measurable rate to assert against.
    time.sleep(1.1); ej.step(); ej._flush()
    time.sleep(1.1); ej.step(); ej._flush()
    e1 = jobs("eta countdown")[0].get("eta_seconds")
    check("eta: an estimate exists once items have landed", e1 is not None)
    time.sleep(1.3)
    e2 = jobs("eta countdown")[0].get("eta_seconds")
    check("eta: the estimate is comfortably above the sample gap",
          e1 is not None and e1 > 3.0, str(e1))
    check("eta: time left counts down between steps",
          e1 is not None and e2 is not None and e2 < e1, f"{e1} -> {e2}")
    check("eta: never negative", e2 is None or e2 >= 0, str(e2))

    # A heartbeat that does not move the count must not re-baseline the rate:
    # done_at tracks the count, updated_at tracks any traffic.
    before = jobs("eta countdown")[0].get("eta_seconds")
    ej.step(0); ej._flush()
    after = jobs("eta countdown")[0].get("eta_seconds")
    check("eta: a heartbeat that moves no items does not reset the estimate",
          after is not None and before is not None and after <= before + 0.5,
          f"{before} -> {after}")

    row = jobs("eta countdown")[0]
    check("eta: done_at is tracked separately from updated_at",
          row.get("done_at") is not None and row.get("done_at") != row.get("updated_at"),
          f"done_at={row.get('done_at')} updated_at={row.get('updated_at')}")

# status line renderer --------------------------------------------------------
_sl = importlib.util.spec_from_file_location("pcstatus", HERE / "statusline.py")
statusline = importlib.util.module_from_spec(_sl)
_sl.loader.exec_module(statusline)

check("statusline: idle renders nothing", statusline.render("no-such-session") is None)
check("statusline: bar is exactly the requested width",
      len(statusline.bar(0.5, 10)) == 10, repr(statusline.bar(0.5, 10)))
check("statusline: a full bar has no empty cells",
      statusline.bar(1.0, 8) == "\u2588" * 8, repr(statusline.bar(1.0, 8)))
check("statusline: an empty bar has no filled cells",
      statusline.bar(0.0, 8) == "\u2591" * 8, repr(statusline.bar(0.0, 8)))
_evil = statusline._row({"name": "build\x1b[2J\x1b[H\u202egnp", "progress": 0.5,
                         "progress_mode": "items", "done": 1, "total": 2,
                         "state": "running", "agent": "a\x1b[31m"}, 10)
check("statusline: a job name cannot inject an escape sequence into the prompt",
      "\x1b[2J" not in _evil and "\x1b[H" not in _evil and "\u202e" not in _evil
      and "\x1b[31m" not in _evil and "build" in _evil, repr(_evil))
_evil2 = statusline._row({"name": "n", "progress": 0.5, "progress_mode": "items",
                          "done": "\x1b[2J", "total": "\x1b[31m9", "state": "running",
                          "eta_seconds": "soon", "detached": "x\x1b[H"}, 10,
                         folded=[{"name": "f\x1b[0m", "progress": "half"}])
check("statusline: every printed field is checked, not only the name",
      _evil2.count("\x1b") == _evil.count("\x1b") - _evil.count("\x1b[31m")
      and "\x1b[2J" not in _evil2 and "\x1b[H" not in _evil2, repr(_evil2))
check("statusline: a non-numeric progress draws an empty bar instead of crashing",
      "0%" in statusline._row({"name": "n", "progress": "half", "state": "running"}, 10))
_big = statusline._row({"name": "n", "progress": 1e308, "progress_mode": "items",
                        "done": 10 ** 5000, "total": 10 ** 5000, "state": "running",
                        "eta_seconds": 10 ** 400, "depth": 10 ** 9}, 10,
                       folded=[{"name": "f", "progress": 1e308}])
check("statusline: absurd numbers cannot crash the row or flood the line",
      len(_big) < 200 and "0%" in _big, "%d chars: %r" % (len(_big), _big[:120]))
check("statusline: a number out of its honest range is refused",
      statusline._num(1.5, 0, 1) is None and statusline._num(-1) is None
      and statusline._num(float("nan")) is None and statusline._num(True) is None
      and statusline._num(10 ** 13) is None and statusline._num(1, 0, 1) == 1
      and statusline._num(0) == 0)
import re as _re


class _CountingPattern:
    """Stands in for the compiled pattern to see how much text it is handed."""
    seen = 0

    def sub(self, repl, text):
        _CountingPattern.seen = max(_CountingPattern.seen, len(text))
        return _re.sub("[\x00-\x1f]", repl, text)


_real, statusline._UNSAFE = statusline._UNSAFE, _CountingPattern()
_long = statusline._safe({"uid": "u", "name": "a\x1b" * 500_000, "state": "running"})
statusline._UNSAFE = _real
check("statusline: a huge field is cut BEFORE it is scanned, not after",
      _CountingPattern.seen <= statusline.MAX_TEXT and len(_long["name"]) == statusline.MAX_TEXT
      and "\x1b" not in _long["name"], "scanned %d chars" % _CountingPattern.seen)
check("statusline: _safe keeps honest values untouched",
      statusline._safe({"uid": "u", "name": "reel 03 \u2713", "progress": 0.25, "done": 3,
                        "total": 12, "depth": 1, "state": "running"})
      == {"uid": "u", "name": "reel 03 \u2713", "state": "running", "progress_mode": None,
          "parent": None, "agent": None, "detached": None, "progress": 0.25, "done": 3,
          "total": 12, "eta_seconds": None, "depth": 1})
check("statusline: no gap between filled and empty runs",
      " " not in statusline.bar(2 / 18, 18), repr(statusline.bar(2 / 18, 18)))

os.environ["CLAUDE_CODE_SESSION_ID"] = "sess-SL"
with progress.Job("sl job", total=4) as slj:
    slj.step(); slj._flush()
    out = statusline.render("sess-SL")
    check("statusline: renders this session's live job",
          out is not None and "sl job" in out, repr(out))
    check("statusline: an items job shows its counts", out and "1/4" in out, repr(out))
    check("statusline: another session sees nothing",
          statusline.render("sess-OTHER") is None)
    os.environ["CLAUDE_CODE_AGENT"] = "explorer"
    with progress.Job("agent job", total=2) as aj:
        aj.step(); aj._flush()
        out = statusline.render("sess-SL")
        check("statusline: subagent work is labelled with the agent",
              out and "explorer: agent job" in out, repr(out))
os.environ.pop("CLAUDE_CODE_AGENT", None)
os.environ.pop("CLAUDE_CODE_SESSION_ID", None)

_port = os.environ.get("PROGRESS_PORT")
os.environ["PROGRESS_PORT"] = "1"          # nothing listening
check("statusline: a dead daemon renders nothing, never raises",
      statusline.render("sess-SL") is None)
if _port:
    os.environ["PROGRESS_PORT"] = _port

# name-stem similarity (0.4.0) ----------------------------------------------
check("stem: paths and digits stripped",
      progress.name_stem("make /home/a/proj -j8") == "make j",
      repr(progress.name_stem("make /home/a/proj -j8")))
check("stem: 'reel 03 restore' == 'reel 07 restore'",
      progress.name_stem("reel 03 restore") == progress.name_stem("reel 07 restore"))
check("stem: distinct commands stay distinct",
      progress.name_stem("maven build") != progress.name_stem("pytest run"))
check("stem: pure-path name falls back to lowercased original",
      progress.name_stem("/usr/bin/x") == "/usr/bin/x")

_now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
_hist = [
    {"name": "remote build 01", "name_stem": "remote build",
     "kind": "local", "project": "projA", "status": "done", "seconds": 100,
     "finished_at": _now},
    {"name": "remote build /tmp/b2", "kind": "local", "project": "projA",
     "status": "done", "seconds": 300, "finished_at": _now},  # pre-0.4 row: no stem, derived on read
]
t2 = progress.Tracker()
t2.history = _hist
job_new = {"name": "remote build /tmp/b3", "kind": "local", "project": "projA",
           "status": "running", "done": 0,
           "started_at": (datetime.now(timezone.utc) - timedelta(seconds=50)
                          ).strftime("%Y-%m-%dT%H:%M:%SZ")}
ratio, mode = t2.progress(job_new)
check("eta~: unseen name borrows stem-mates' median, labelled eta~",
      mode == "eta~" and ratio is not None and 0.2 < ratio < 0.3,
      f"{mode} {ratio}")
job_exact = dict(job_new, name="remote build 01")
check("eta~: exact-name history still wins with plain eta",
      t2.progress(job_exact)[1] == "eta")
job_other_proj = dict(job_new, project="projB")
check("eta~: falls through to global stem when project has none",
      t2.progress(job_other_proj)[1] == "eta~")
job_alien = dict(job_new, name="database vacuum")
check("eta~: unrelated stem still creeps",
      t2.progress(job_alien)[1] == "creep")

# history enrichment (0.4.0) -------------------------------------------------
rows_now = progress.load_history()
enriched = [r for r in rows_now if r.get("name_stem")]
check("history: records carry name_stem/project context",
      enriched and all("project" in r for r in enriched),
      f"{len(enriched)} enriched of {len(rows_now)}")

# retention (0.4.0) -----------------------------------------------------------
_old = (datetime.now(timezone.utc) - timedelta(days=9)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
_fresh = (datetime.now(timezone.utc) - timedelta(days=2)
          ).strftime("%Y-%m-%dT%H:%M:%SZ")
_rows = [
    {"name": "dead job", "status": "done", "seconds": 5, "finished_at": _old},
    {"name": "alive job", "status": "done", "seconds": 5, "finished_at": _old},
    {"name": "alive job", "status": "done", "seconds": 6, "finished_at": _fresh},
    {"name": "no-ts job", "status": "done", "seconds": 7},
]
kept = progress.prune_history(_rows)
names = {r["name"] for r in kept}
check("retention: a name idle >7d loses every row", "dead job" not in names)
check("retention: one fresh run keeps the whole name (old rows too)",
      len([r for r in kept if r["name"] == "alive job"]) == 2)
check("retention: a row that can't prove freshness goes with the dead",
      "no-ts job" not in names)
os.environ["PROGRESS_HISTORY_DAYS"] = "30"
check("retention: PROGRESS_HISTORY_DAYS widens the window",
      "dead job" in {r["name"] for r in progress.prune_history(_rows)})
os.environ.pop("PROGRESS_HISTORY_DAYS", None)

# daemon startup persists the prune
hist_path = TMP / "history.jsonl"
with open(hist_path, "a", encoding="utf-8") as f:
    f.write(json.dumps({"name": "ancient", "status": "done", "seconds": 3,
                        "finished_at": _old}) + "\n")
progress.Tracker()   # init prunes + rewrites the file
on_disk = hist_path.read_text()
check("retention: daemon startup rewrites the file without dead names",
      "ancient" not in on_disk and on_disk.strip())

# upgrade handshake (0.4.0) ---------------------------------------------------
health = progress._get_json("/health")
check("upgrade: /health reports the plugin version",
      health and health.get("version") == progress.plugin_version(),
      repr(health))
check("upgrade: dev sorts below every release",
      progress._ver_tuple("dev") < progress._ver_tuple("0.0.1"))
check("upgrade: version tuples order numerically",
      progress._ver_tuple("0.10.0") > progress._ver_tuple("0.9.9"))
old_pid = health["pid"]
check("upgrade: /shutdown is acknowledged", progress._post_plain("/shutdown"))
check("upgrade: daemon releases the port on request",
      wait_for(lambda: progress._get_json("/health", timeout=0.3) is None))
progress._spawn_attempted = False
check("upgrade: ensure_daemon respawns after a shutdown",
      progress.ensure_daemon())
new_health = progress._get_json("/health")
check("upgrade: the replacement is a new process",
      new_health and new_health["pid"] != old_pid)

# whats-new hook (0.5.0) — one notice per install/upgrade, with setup offer --
HOOK_WN = HERE.parent / "hooks" / "whats-new.py"
wn_marker = TMP / "last-version"
wn_marker.unlink(missing_ok=True)


def run_whats_new():
    return subprocess.run([sys.executable, str(HOOK_WN)], env=dict(os.environ),
                          capture_output=True, text=True).stdout

out = run_whats_new()
check("whats-new: fresh install emits one orientation notice",
      "newly installed" in out, out[:120])
check("whats-new: unwired status line makes the notice offer setup",
      "NOT set up" in out, out[:200])
check("whats-new: marker recorded", wn_marker.exists())
check("whats-new: second session is silent", run_whats_new() == "")
wn_marker.write_text("0.0.1\n")
out = run_whats_new()
check("whats-new: version change emits an upgrade notice with both versions",
      "upgraded 0.0.1" in out and progress.plugin_version() in out, out[:160])

# statusline_seen (0.5.0) — the wired-renderer signal --------------------------
check("statusline_seen: fresh daemon reports false",
      (progress._get_json("/health") or {}).get("statusline_seen") is False)

HOOK_SP = HERE.parent / "hooks" / "suggest-progress.py"


def run_suggest(cmd):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
    return subprocess.run([sys.executable, str(HOOK_SP)], env=dict(os.environ),
                          input=payload, capture_output=True, text=True).stdout

(TMP / ".statusline-tipped").unlink(missing_ok=True)
out = run_suggest("mvn -B verify")
check("advisory: maven suggests the tap, not the run wrapper",
      "progress_tap.py" in out, out[:200])
check("advisory: unwired status line gets the weekly tip",
      "status" in out and "line" in out and (TMP / ".statusline-tipped").exists(),
      out[:200])
check("advisory: tip marker suppresses a second tip within the week",
      "set up the progress status line" not in run_suggest("mvn -B verify"))
out = run_suggest("git clone https://example.com/big.git")
check("advisory: git clone is long-running now, tap-suggested with --pattern git",
      "progress_tap.py" in out and "--pattern git" in out, out[:200])
check("advisory: plain git stays short-safe",
      run_suggest("git status") == "")

# The band mod (0.7.0) polls with view=mod. It must not read as a status line:
# its `auto` mode hides when one is wired, and it would be seeing itself.
_mod = progress._get_json("/jobs?session=mod-probe&view=mod") or {}
check("view=mod: the mod's own poll does not count as a wired status line",
      _mod.get("statusline_seen") is False
      and (progress._get_json("/health") or {}).get("statusline_seen") is False)
check("view=mod: it is still a session-filtered view",
      _mod.get("jobs") == [], str(_mod.get("jobs"))[:120])

progress._get_json("/jobs?session=wired-probe")
check("statusline_seen: flips true after one session-filtered poll",
      (progress._get_json("/health") or {}).get("statusline_seen") is True)
check("statusline_seen: /jobs carries the flag for the page banner",
      (progress._get_json("/jobs?state=all") or {}).get("statusline_seen") is True)

# progress_tap (0.5.0) — measured bars from a build's own output --------------
TAP = HERE / "progress_tap.py"
MAVEN_OUT = ("[INFO] Scanning...\n"
             "[INFO] Building acme-core 1.0 [1/3]\n"
             "[INFO] Building acme-api 1.0 [2/3]\n"
             "[INFO] Building acme-dist 1.0 [3/3]\n"
             "[INFO] BUILD SUCCESS\n")
r = subprocess.run([sys.executable, str(TAP), "tap maven"], env=dict(os.environ),
                   input=MAVEN_OUT.encode(), capture_output=True)
check("tap: stdin forwarded byte-for-byte", r.stdout == MAVEN_OUT.encode())
check("tap: exits 0", r.returncode == 0)
row = (jobs("tap maven") or [{}])[0]
check("tap: maven reactor line becomes a measured 3/3 done job",
      row.get("done") == 3 and row.get("total") == 3
      and row.get("state") == "done", str(row)[:120])

GIT_OUT = ("Cloning into 'big'...\n"
           "Receiving objects:  10% (10/100)\r"
           "Receiving objects: 100% (100/100), done.\n"
           "Resolving deltas: 100% (40/40), done.\n")
r = subprocess.run([sys.executable, str(TAP), "tap git", "--pattern", "git"],
                   env=dict(os.environ), input=GIT_OUT.encode(),
                   capture_output=True)
check("tap: git \\r-separated updates forwarded unchanged",
      r.stdout == GIT_OUT.encode())
row = (jobs("tap git") or [{}])[0]
check("tap: git phases parse through carriage returns (deltas 40/40)",
      row.get("done") == 40 and row.get("total") == 40
      and row.get("state") == "done", str(row)[:120])

# Patterns beyond Maven and git (0.8.0). Each case is the tool's real piped
# output shape, and what the tap must make of it: (pattern, stdin, done, total).
TAP_CASES = {
    "docker": ("#5 [build 1/4] FROM alpine\n#6 [build 2/4] RUN apk add make\n"
               "#7 [build 4/4] RUN make\n#8 DONE 1.2s\n", 4, 4),
    "ninja": ("[1/3] Building CXX object a.o\n[2/3] Building CXX object b.o\n"
              "[3/3] Linking CXX executable app\n", 3, 3),
    "ratio": ("processed 10/40 files\nprocessed 40/40 files\nat 12.5/s, see a/b/c\n", 40, 40),
    "pytest": ("collected 12 items\n\ntests/test_a.py ....   [ 33%]\n"
               "tests/test_b.py ........ [100%]\n\n12 passed in 0.4s\n", 100, 100),
    "cmake": ("[ 25%] Building C object a.o\n[ 50%] Building C object b.o\n"
              "[100%] Linking C executable app\n[100%] Built target app\n", 100, 100),
    "rsync": ("      1,234,567  42%    1.23MB/s    0:00:12\r"
              "      2,939,444 100%    1.50MB/s    0:00:01 (xfr#3, to-chk=0/3)\n", 100, 100),
    "percent": ("downloading... 30%\ndownloading... 100% done, 250% of quota\n", 100, 100),
    "gradle": ("> Task :app:compileJava\n> Task :app:processResources NO-SOURCE\n"
               "> Task :app:classes\n\nBUILD SUCCESSFUL in 2s\n", 3, None),
    "cargo": ("   Compiling serde v1.0.203\n   Compiling app v0.1.0 (/x)\n"
              "    Finished dev [unoptimized] target(s) in 3.1s\n", 2, None),
    "go": ("ok  \texample.com/a\t0.41s\n--- FAIL: TestX (0.00s)\nFAIL\texample.com/b\t0.02s\n"
           "?   \texample.com/c\t[no test files]\n", 3, None),
    "jest": ("PASS src/a.test.ts\nFAIL src/b.test.tsx\n \u2713 src/c.spec.js (3)\n"
             "Tests: 1 failed, 5 passed\n", 3, None),
    "dotnet": ("  Determining projects to restore...\n  App.Core -> /src/bin/App.Core.dll\n"
               "  App -> /src/bin/App.dll\nBuild succeeded.\n", 2, None),
    "terraform": ("aws_s3_bucket.a: Creating...\naws_s3_bucket.a: Creation complete after 2s\n"
                  "aws_iam_role.b: Modifications complete after 1s\nApply complete!\n", 2, None),
    "ansible": ("PLAY [all] ***\nTASK [Gathering Facts] ***\nok: [h1]\n"
                "TASK [install packages] ***\nchanged: [h1]\n", 2, None),
}
for _pat, (_text, _done, _total) in TAP_CASES.items():
    r = subprocess.run([sys.executable, str(TAP), f"tap {_pat}", "--pattern", _pat],
                       env=dict(os.environ), input=_text.encode(), capture_output=True)
    row = (jobs(f"tap {_pat}") or [{}])[0]
    check(f"tap: {_pat} output is forwarded unchanged and read as {_done}"
          + (f"/{_total}" if _total else " counted"),
          r.stdout == _text.encode() and row.get("done") == _done
          and row.get("total") == _total and row.get("state") == "done",
          "done=%s total=%s state=%s" % (row.get("done"), row.get("total"), row.get("state")))

# Half the job is NOT matching: build noise must not move a bar.
for _pat, _noise in {
        "ninja": "ninja: Entering directory `build'\nwarning: 3/4 of the cache is stale\n",
        "pytest": "coverage: 87%\nplatform linux -- Python 3.12\n",
        "docker": "#3 [internal] load metadata\n#4 DONE 0.1s\nsee step 2/3 of the guide\n",
        "gradle": "Task :app:test FAILED\n1 actionable task: 1 executed\n",
        "go": "go: downloading example.com/x v1.2.3\nPASS\n",
        "ratio": "version 1.2/3.4, path a/b, date 2026/10/06, 3.5/4 stars\n",
        "percent": "took 1.5% longer, 250% of baseline\n"}.items():
    subprocess.run([sys.executable, str(TAP), f"noise {_pat}", "--pattern", _pat],
                   env=dict(os.environ), input=_noise.encode(), capture_output=True)
    row = (jobs(f"noise {_pat}") or [{}])[0]
    check(f"tap: {_pat} ignores lines that only look like progress",
          not row.get("done") and row.get("state") == "done",
          "done=%s total=%s" % (row.get("done"), row.get("total")))

r = subprocess.run([sys.executable, str(TAP), "tap typo", "--pattern", "gradel"],
                   env=dict(os.environ), input=MAVEN_OUT.encode(), capture_output=True)
row = (jobs("tap typo") or [{}])[0]
check("tap: an unknown pattern says so on stderr, forwards stdout, and does not fake Maven",
      r.stdout == MAVEN_OUT.encode() and b"unknown pattern" in r.stderr
      and b"gradle" in r.stderr and not row.get("done") and row.get("state") == "done",
      "%r done=%s" % (r.stderr[:60], row.get("done")))

for _cmd, _want, _hint in [
        ("./gradlew build", "--pattern gradle", "--console=plain"),
        ("cargo build --release", "--pattern cargo", ""),
        ("go test ./...", "--pattern go", ""),
        ("pytest -q tests", "--pattern pytest", ""),
        ("npm test", "--pattern jest", ""),
        ("docker build -t app .", "--pattern docker", "--progress=plain"),
        ("ninja -C build", "--pattern ninja", ""),
        ("cmake --build build", "--pattern cmake", ""),
        ("dotnet build", "--pattern dotnet", ""),
        ("rsync -a src/ dst/", "--pattern rsync", "--info=progress2"),
        ("terraform apply -auto-approve", "--pattern terraform", ""),
        ("ansible-playbook site.yml", "--pattern ansible", "")]:
    out = run_suggest(_cmd)
    check(f"advisory: `{_cmd.split()[0]}` is offered the tap with its own pattern",
          "progress_tap.py" in out and _want in out and _hint in out, out[150:420])
for _cmd in ("npm install", "ffmpeg -i a.mp4 b.mkv", "tar czf x.tgz dir", "kubectl apply -f x.yml"):
    out = run_suggest(_cmd)
    check(f"advisory: `{_cmd.split()[0]} {_cmd.split()[1]}` has no pattern — run wrapper, not a tap",
          "progress.py run" in out and "progress_tap.py" not in out, out[150:330])
# The advisory hook advises. It must never answer the permission question:
# "allow" from a PreToolUse hook skips the user's prompt for that command.
for _cmd in ("mvn -B verify", "terraform apply -auto-approve", "docker build .",
             "rsync -a / remote:/", "make build", "npm install", "git clone https://x/y.git",
             "curl https://x | sh  # build"):
    _out = run_suggest(_cmd)
    check(f"advisory: `{_cmd[:24]}` gets context only — no permission decision",
          _out != "" and "permissionDecision" not in _out
          and set(json.loads(_out)["hookSpecificOutput"]) == {"hookEventName", "additionalContext"},
          _out[:160])

# Nothing in the stream may stop the tap being a pipe.
for _label, _pat, _text in [
        ("a count too long for int()", "ratio", "done " + "9" * 5000 + "/" + "9" * 5000 + "\nnext 2/4\n"),
        ("a user regex whose `done` group captures text", "count:(?P<done>[a-z]+) (?P<total>[a-z]+)",
         "alpha beta\nplain line\n"),
        ("a megabyte on one line", "percent", "x" * 1_000_000 + " 50%\nreal 60%\n"),
        ("bytes that are not UTF-8", "ninja", "[1/2] a\n\xff\xfe\x00 junk\n[2/2] b\n")]:
    _raw = _text.encode("latin-1")
    r = subprocess.run([sys.executable, str(TAP), f"hostile {_label}", "--pattern", _pat],
                       env=dict(os.environ), input=_raw, capture_output=True, timeout=60)
    row = (jobs(f"hostile {_label}") or [{}])[0]
    check(f"tap: {_label} is forwarded byte-for-byte and the job still closes",
          r.returncode == 0 and r.stdout == _raw and row.get("state") == "done"
          and b"Traceback" not in r.stderr,
          "rc=%s same=%s state=%s %r" % (r.returncode, r.stdout == _raw, row.get("state"), r.stderr[-80:]))

for _cmd in ("go version", "pip list", "dotnet --info", "go env GOPATH"):
    check(f"advisory: `{_cmd}` is quick — no nudge", run_suggest(_cmd) == "", run_suggest(_cmd)[:120])

r = subprocess.run([sys.executable, str(TAP), "quiet job", "--quiet"],
                   env=dict(os.environ), input=b"hello\n", capture_output=True)
check("tap: --quiet is a pure cat, registers nothing",
      r.stdout == b"hello\n" and not jobs("quiet job"))

env_dead = dict(os.environ, PROGRESS_PORT="1")
r = subprocess.run([sys.executable, str(TAP), "dead daemon"], env=env_dead,
                   input=MAVEN_OUT.encode(), capture_output=True, timeout=30)
check("tap: dead daemon degrades to cat, still exit 0",
      r.stdout == MAVEN_OUT.encode() and r.returncode == 0)

# examples/ (0.8.0) — every shipped example must actually run, tracked and not -
import shutil
EX = HERE.parent / "examples"
_ex_env = dict(os.environ, PROGRESS_CLI=f"{sys.executable} {HERE / 'progress.py'}",
               PROGRESS_LIB=str(HERE), DELAY="0.01", CLAUDE_CODE_SESSION_ID="sess-EX")
_ex_env.pop("PROGRESS_PARENT", None)
_bare = {k: v for k, v in _ex_env.items() if k not in ("PROGRESS_CLI", "PROGRESS_LIB")}


def _ex(cmd, env, cwd=None):
    return subprocess.run(cmd, env=env, cwd=cwd, capture_output=True, text=True, timeout=120)


def _job(name, state=None):
    """A sess-EX job by name — and by state, when a name has run twice."""
    rows = [j for j in (progress._get_json("/jobs?state=all") or {}).get("jobs", [])
            if j.get("name") == name and j.get("session") == "sess-EX"
            and (state is None or j.get("state") == state)]
    return rows[-1] if rows else {}


for _file, _cmd, _name, _want in [
        ("bash-loop.sh", ["bash", str(EX / "bash-loop.sh")], "bash loop", (20, 20)),
        ("python_job.py", [sys.executable, str(EX / "python_job.py")], "python transcode", (8, 8)),
        ("node-job.mjs", ["node", str(EX / "node-job.mjs")], "node render", (40, 40)),
        ("go-job", ["go", "run", "."], "go reindex", (24, 24))]:
    if not shutil.which(_cmd[0]):
        check(f"example {_file}: runs and reports itself", True, f"{_cmd[0]} absent — skipped")
        continue
    _cwd = str(EX / "go-job") if _file == "go-job" else None
    r = _ex(_cmd, _ex_env, _cwd)
    row = _job(_name)
    check(f"example {_file}: runs and reports itself to completion",
          r.returncode == 0 and (row.get("done"), row.get("total")) == _want
          and row.get("state") == "done",
          "rc=%s done=%s/%s state=%s %s" % (r.returncode, row.get("done"), row.get("total"),
                                            row.get("state"), r.stderr[-120:]))
    check(f"example {_file}: runs the same with no channel at all",
          _ex(_cmd, _bare, _cwd).returncode == 0)

r = _ex(["bash", str(EX / "bash-pipeline.sh")], _ex_env)
_p = _job("example pipeline", "done")
_kids = [j for j in (progress._get_json("/jobs?state=all") or {}).get("jobs", [])
         if j.get("parent") == _p.get("uid")]
check("example bash-pipeline.sh: three stages nest under the pipeline, all done",
      r.returncode == 0 and _p.get("state") == "done" and _p.get("done") == 3
      and sorted(k.get("name") for k in _kids) == ["bash loop", "stage: fetch", "stage: package"]
      and all(k.get("state") == "done" for k in _kids),
      "pipeline=%s kids=%s" % (_p.get("state"), [(k.get("name"), k.get("state")) for k in _kids]))
check("example bash-pipeline.sh: the unmodified sub-script nested itself",
      any(k.get("name") == "bash loop" and k.get("total") == 6 for k in _kids))
r = _ex(["bash", str(EX / "bash-loop.sh")], dict(_ex_env, FAIL_AT="3"))
row = _job("bash loop", "failed")
check("example bash-loop.sh: a failure is reported as failed, with where it stopped",
      r.returncode == 3 and row.get("state") == "failed" and "item 3" in str(row.get("error")),
      "rc=%s state=%s error=%s" % (r.returncode, row.get("state"), row.get("error")))
r = _ex(["bash", str(EX / "bash-pipeline.sh")], dict(_ex_env, FAIL_AT="4"))
_p = _job("example pipeline", "failed")
check("example bash-pipeline.sh: a failed stage fails the pipeline and leaves no open row",
      r.returncode != 0 and _p.get("state") == "failed"
      and not [j for j in (progress._get_json("/jobs") or {}).get("jobs", [])
               if j.get("session") == "sess-EX" and j.get("state") == "running"],
      "rc=%s pipeline=%s" % (r.returncode, _p.get("state")))
if shutil.which("make"):
    r = _ex(["make", "-s", "-f", str(EX / "Makefile"), "all"], _ex_env)
    check("example Makefile: targets run as timed jobs",
          r.returncode == 0 and _job("example build").get("state") == "done"
          and _job("example lint").get("state") == "done", r.stderr[-160:])
    check("example Makefile: runs the same with no channel at all",
          _ex(["make", "-s", "-f", str(EX / "Makefile"), "all"], _bare).returncode == 0)
_taps_doc = (EX / "taps.md").read_text()
_tap_mod = importlib.util.spec_from_file_location("pctap", HERE / "progress_tap.py")
_tapm = importlib.util.module_from_spec(_tap_mod)
_tap_mod.loader.exec_module(_tapm)
_named = set(_re.findall(r"--pattern (?:'count:|)([a-z]+)", _taps_doc)) - {"count"}
check("examples/taps.md: every pattern it names exists, and every pattern is documented",
      _named <= set(_tapm.PATTERNS) and set(_tapm.PATTERNS) - _named <= {"maven"},
      "unknown=%s undocumented=%s" % (sorted(_named - set(_tapm.PATTERNS)),
                                      sorted(set(_tapm.PATTERNS) - _named)))

big = urllib.request.Request(progress.base_url() + "/jobs", data=b"x" * (300 * 1024),
                             headers={"Content-Type": "application/json"}, method="POST")
try:
    urllib.request.urlopen(big, timeout=5)
    _code = 200
except urllib.error.HTTPError as e:
    _code = e.code
except Exception as e:                      # the daemon may close before the body is sent
    _code = type(e).__name__
check("daemon: an oversized POST body is refused, not read",
      _code in (413, "ConnectionResetError", "BrokenPipeError", "URLError"), str(_code))
check("daemon: still answering after the refusal",
      (progress._get_json("/health") or {}).get("ok") is True)

# statusline_wrap (0.5.0) ------------------------------------------------------
WRAP = HERE / "statusline_wrap.py"
os.environ["CLAUDE_CODE_SESSION_ID"] = "sess-WRAP"
with progress.Job("wrap job", total=4) as wj:
    wj.step(); wj._flush()
    r = subprocess.run([sys.executable, str(WRAP), "--", "echo", "MYLINE"],
                       env=dict(os.environ),
                       input=json.dumps({"session_id": "sess-WRAP"}).encode(),
                       capture_output=True)
    out = r.stdout.decode()
    check("wrap: existing status line output kept, progress rows appended",
          out.startswith("MYLINE") and "wrap job" in out, out[:120])
    r = subprocess.run([sys.executable, str(WRAP), "--", "false"],
                       env=dict(os.environ),
                       input=json.dumps({"session_id": "sess-WRAP"}).encode(),
                       capture_output=True)
    check("wrap: failing wrapped command still renders the progress half",
          "wrap job" in r.stdout.decode())
os.environ.pop("CLAUDE_CODE_SESSION_ID", None)

# sub-jobs (0.6.0) -------------------------------------------------------------
# The first three checks are the defects of the manual pattern this replaces:
# two top-level jobs with the child's indent baked into its NAME. Each was
# reproduced on a scratch daemon before any of this code existed.
os.environ["CLAUDE_CODE_SESSION_ID"] = "sess-TREE"


def _tree_rows(q="?session=sess-TREE"):
    return [r for r in _jobs(q) if r.get("session") == "sess-TREE"]


with progress.Job("tree parent", total=34) as tp:
    tp.step(26); tp._flush()
    time.sleep(0.05)
    with tp.child("ground-round", total=619) as tc:
        tc.step(549); tc._flush()          # the child updated LAST
        rows = _tree_rows()
        names = [r["name"] for r in rows]
        check("tree: parent renders before its child even when the child "
              "updated last",
              names.index("tree parent") < names.index("ground-round"),
              str(names))
        crow = [r for r in rows if r["name"] == "ground-round"][0]
        prow = [r for r in rows if r["name"] == "tree parent"][0]
        check("tree: child carries its parent uid and depth 1",
              crow.get("parent") == tp.uid and crow.get("depth") == 1
              and prow.get("depth") == 0, str((crow.get("parent"), crow.get("depth"))))
        check("tree: child keeps its PLAIN name (exact-name ETA learning is "
              "shared with standalone runs)", crow["name"] == "ground-round")
        check("tree: child inherits the parent's session",
              crow.get("session") == "sess-TREE")
        # Rolled-up parent bar: (26 + 549/619) / 34, labelled so it is never
        # mistaken for a plain count.
        want = (26 + 549 / 619) / 34
        check("rollup: parent bar includes the running child's fraction",
              prow["progress_mode"] == "items+sub"
              and abs(prow["progress"] - want) < 1e-6,
              f"{prow.get('progress_mode')} {prow.get('progress')} want {want}")
        out = statusline.render("sess-TREE") or ""
        lines = out.splitlines()
        check("statusline: child row is indented under its parent",
              len(lines) >= 2 and "tree parent" in lines[0]
              and "↳ ground-round" in lines[1], repr(out)[:200])

# defect 2: parent ends, child must not linger as a dangling ↳ row
r = [x for x in jobs("ground-round") if x.get("parent") == tp.uid][0]
check("cascade: exiting the parent closes a still-open child",
      r["state"] != "running", r["state"])

try:
    with progress.Job("boom parent", total=3) as bp:
        with bp.child("boom child", total=5) as bc:
            bc.step()
            raise RuntimeError("stage blew up")
except RuntimeError:
    pass
bc_row = jobs("boom child")[0]
bp_row = jobs("boom parent")[0]
check("cascade: an exception fails child AND parent",
      bc_row["state"] == "failed" and bp_row["state"] == "failed",
      f"{bc_row['state']} {bp_row['state']}")

# A child opened without the context manager and left open when the parent
# closes is cancelled by the parent, naming why.
with progress.Job("leaky parent", total=1) as lp:
    leak = lp.child("leaky child", total=9)
    leak.__enter__()
    leak.step(); leak._flush()
lr = jobs("leaky child")[0]
check("cascade: parent exit cancels a child left open, with a reason",
      lr["state"] == "cancelled" and "parent" in (lr.get("error") or ""),
      f"{lr['state']} {lr.get('error')}")

# Server-side derivation when a producer did NOT cascade (a raw POST client):
# the orphaned child moves to the top level and is labelled, never hidden.
puid, cuid = "a" * 32, "b" * 32
base = {"kind": "local", "session": "sess-TREE", "pid": os.getpid(),
        "host": os.uname().nodename}
progress._post_job(dict(base, uid=puid, name="raw parent", total=4, done=1,
                        status="running"))
progress._post_job(dict(base, uid=cuid, name="raw child", total=10, done=3,
                        status="running", parent=puid))
progress._post_job(dict(base, uid=puid, name="raw parent", total=4, done=1,
                        status="cancelled"))
rc = [x for x in _tree_rows() if x["name"] == "raw child"]
check("detached: child of an ended parent stays visible at depth 0",
      rc and rc[0]["depth"] == 0, str(rc)[:160])
check("detached: and says its parent ended",
      rc and "parent" in (rc[0].get("detached") or ""), str(rc)[:160])
progress._post_job(dict(base, uid=cuid, name="raw child", total=10, done=3,
                        status="done"))

# Parent time-left rolls up: the running step's own time-left plus the
# remaining WHOLE steps at the parent's per-step rate. Synthetic timestamps
# make it deterministic: parent 10/20 done over 100s (10s/step), child 50/100
# over 30s (0.6s/item, so 30s left). Rolled up: 30 + (20-10-1)*10 = 120s.
# The parent alone would claim 100s — the in-flight step counted as untouched.
_now_dt = datetime.now(timezone.utc)
_ago = lambda s: (_now_dt - timedelta(seconds=s)).strftime("%Y-%m-%dT%H:%M:%SZ")
eu_p, eu_c = "c" * 32, "d" * 32
progress._post_job(dict(base, uid=eu_p, name="eta rollup parent", total=20,
                        done=10, status="running", started_at=_ago(100)))
progress._post_job(dict(base, uid=eu_c, name="eta rollup child", total=100,
                        done=50, status="running", started_at=_ago(30),
                        parent=eu_p))
_er = {r["name"]: r for r in _tree_rows()}
_pe = (_er.get("eta rollup parent") or {}).get("eta_seconds")
_ce = (_er.get("eta rollup child") or {}).get("eta_seconds")
check("eta: child's own time-left is unchanged by nesting",
      _ce is not None and abs(_ce - 30) < 3, str(_ce))
check("eta: parent time-left = running step's time-left + remaining steps",
      _pe is not None and abs(_pe - 120) < 4, f"{_pe} (want ~120, alone ~100)")
# A child with no rate yet must not blank or guess the parent's estimate.
eu_c2 = "e" * 32
progress._post_job(dict(base, uid=eu_c, name="eta rollup child", total=100,
                        done=50, status="done"))
progress._post_job(dict(base, uid=eu_c2, name="eta rollup fresh child",
                        total=100, done=0, status="running", parent=eu_p))
_pe2 = {r["name"]: r for r in _tree_rows()}.get("eta rollup parent", {}) \
    .get("eta_seconds")
check("eta: a child with no rate yet leaves the parent's own estimate",
      _pe2 is not None and abs(_pe2 - 100) < 4, str(_pe2))
for _u, _n in ((eu_c2, "eta rollup fresh child"), (eu_p, "eta rollup parent")):
    progress._post_job(dict(base, uid=_u, name=_n, total=20, done=0,
                            status="done"))
check("eta: private rate field does not leak into /jobs rows",
      all("_rate" not in r for r in _jobs("?state=all")))

# defect 3 is structural — the child's plain name — asserted above. The
# history row still records where it ran.
hist = [h for h in progress.load_history() if h.get("name") == "ground-round"]
check("history: child row records its parent's name",
      hist and hist[-1].get("parent_name") == "tree parent", str(hist[-1:])[:160])

# shell path: --parent, and finish cascades to child tokens
PY = [sys.executable, str(HERE / "progress.py")]
envs = dict(os.environ)
ptok = subprocess.run(PY + ["start", "--name", "sh parent", "--total", "3"],
                      env=envs, capture_output=True, text=True).stdout.strip()
ctok = subprocess.run(PY + ["start", "--name", "sh child", "--total", "7",
                            "--parent", ptok],
                      env=envs, capture_output=True, text=True).stdout.strip()
shc = jobs("sh child")
check("shell: --parent reaches the server (not dropped by the token "
      "record's field list)", shc and shc[0].get("parent") == ptok,
      str(shc)[:160])
subprocess.run(PY + ["finish", ptok, "--cancel"], env=envs, capture_output=True)
shc = jobs("sh child")
check("shell: finishing the parent finishes its child tokens",
      shc and shc[0]["state"] == "cancelled"
      and not (TMP / "tokens" / f"{ctok}.json").exists(),
      str(shc)[:160])

# PROGRESS_PARENT: an exported parent nests every sub-script's start, and a
# Python Job (so `progress run` and the tap too) without writing --parent.
ptok2 = subprocess.run(PY + ["start", "--name", "env parent", "--total", "2"],
                       env=envs, capture_output=True, text=True).stdout.strip()
envp = dict(envs, PROGRESS_PARENT=ptok2)
ctok2 = subprocess.run(PY + ["start", "--name", "env child", "--total", "4"],
                       env=envp, capture_output=True, text=True).stdout.strip()
subprocess.run(PY + ["run", "--name", "env run child", "--", "true"],
               env=envp, capture_output=True)
ec = jobs("env child"); er = jobs("env run child")
check("shell: $PROGRESS_PARENT nests a sub-script's start",
      ec and ec[0].get("parent") == ptok2, str(ec)[:160])
check("shell: $PROGRESS_PARENT nests `progress run` too",
      er and er[0].get("parent") == ptok2, str(er)[:160])
subprocess.run(PY + ["finish", ptok2], env=envs, capture_output=True)

# mirror: an optional second poll line is the current sub-step
seq = TMP / "mirror-seq.txt"
seq.write_text("0\n")
poll = TMP / "poll.sh"
poll.write_text(
    "#!/bin/sh\n"
    f"n=$(cat {seq}); echo $((n+1)) > {seq}\n"
    'case $n in\n'
    '  0) printf "1 3\\n5 10 stage-a\\n" ;;\n'
    '  1) printf "2 3\\n4 8 stage-b\\n" ;;\n'
    '  *) printf "3 3\\n" ;;\n'
    'esac\n')
poll.chmod(0o755)
subprocess.run(PY + ["mirror", "--name", "mirrored pipeline", "--source",
                     "test:mirror:1", "--poll-cmd", str(poll),
                     "--interval", "0.3", "--idle-after", "1"],
               env=envs, capture_output=True, timeout=30)
ma = jobs("stage-a"); mb = jobs("stage-b"); mp = jobs("mirrored pipeline")
check("mirror: a sub-step line becomes a child job of the mirror",
      ma and mp and ma[0].get("parent") == mp[0]["uid"], str(ma)[:160])
check("mirror: a new sub-step name finishes the previous child as done",
      ma and ma[0]["state"] == "done" and mb and mb[0]["state"] != "running",
      f"{ma[:1]} {mb[:1]}"[:200])

# status line: never a child without its parent; fold when rows run short
with progress.Job("fold A", total=10) as fa, \
        fa.child("fold A1", total=4) as fa1, \
        progress.Job("fold B", total=10) as fb, \
        fb.child("fold B1", total=4) as fb1:
    for j in (fa, fa1, fb, fb1):
        j.step(); j._flush()
    out = statusline.render("sess-TREE") or ""
    lines = out.splitlines()
    check("statusline: stays within MAX_ROWS with two parents + children",
          len(lines) <= statusline.MAX_ROWS, repr(out)[:200])
    orphan_child = any(("↳" in l) and i == 0 for i, l in enumerate(lines))
    check("statusline: never shows a child row without its parent above it",
          not orphan_child, repr(out)[:200])
    check("statusline: a folded child still appears on its parent's line",
          all(n in out for n in ("fold A", "fold B")) and
          ("fold A1" in out and "fold B1" in out), repr(out)[:300])

os.environ.pop("CLAUDE_CODE_SESSION_ID", None)

# CLI list indents children
lst = "\n".join(progress.cmd_list())
check("cli: list indents a child under its parent",
      "↳ ground-round" in lst, lst[:200])

# cleanup --------------------------------------------------------------------
health = progress._get_json("/health")
if health:
    os.kill(health["pid"], signal.SIGTERM)

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("failed:", ", ".join(FAIL))
sys.exit(1 if FAIL else 0)
