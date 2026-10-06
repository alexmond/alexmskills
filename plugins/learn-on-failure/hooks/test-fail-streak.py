#!/usr/bin/env python3
"""Checks for fail-streak.py. Run directly; exits 1 on any failure."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOOK = HERE / "fail-streak.py"
spec = importlib.util.spec_from_file_location("fail_streak", HOOK)
fs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fs)

failed: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✓' if ok else '✗'} {name}")
    if not ok:
        failed.append(name)
        if detail:
            print(f"      {detail}")


def run(state_dir: str, event: str, command, session: str = "s1", **extra) -> str:
    payload = {"hook_event_name": event, "tool_name": "Bash", "session_id": session,
               "tool_input": {"command": command}, **extra}
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                       env=dict(os.environ, LEARN_ON_FAILURE_STATE=state_dir),
                       capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


FAIL, OK = "PostToolUseFailure", "PostToolUse"

with tempfile.TemporaryDirectory() as d:
    outs = [run(d, FAIL, "npm test") for _ in range(3)]
    check("silent on the first two failures, speaks on the third",
          outs[0] == "" and outs[1] == "" and "failed 3 times" in outs[2], str(outs))
    out = json.loads(outs[2])["hookSpecificOutput"]
    check("the note is context only — no permission decision, and it names the event",
          set(out) == {"hookEventName", "additionalContext"} and out["hookEventName"] == FAIL,
          str(sorted(out)))
    check("the note quotes the command and points at a change of approach",
          "`npm test`" in out["additionalContext"] and "change approach" in out["additionalContext"])
    more = [run(d, FAIL, "npm test") for _ in range(3)]
    check("then quiet until the sixth, so it does not nag every turn",
          more[0] == "" and more[1] == "" and "failed 6 times" in more[2], str(more))

with tempfile.TemporaryDirectory() as d:
    run(d, FAIL, "make build"); run(d, FAIL, "make build")
    run(d, OK, "ls")
    check("any passing command ends the streak",
          run(d, FAIL, "make build") == "" and run(d, FAIL, "make build") == "")
    check("...and it takes three fresh failures to speak again",
          "failed 3 times" in run(d, FAIL, "make build"))

with tempfile.TemporaryDirectory() as d:
    run(d, FAIL, "pytest a"); run(d, FAIL, "pytest a")
    check("a different failing command starts its own count",
          run(d, FAIL, "pytest b") == "" and run(d, FAIL, "pytest b") == ""
          and "failed 3 times" in run(d, FAIL, "pytest b"))

with tempfile.TemporaryDirectory() as d:
    run(d, FAIL, "go   test ./..."); run(d, FAIL, "go test\n./...")
    check("runs that differ only in whitespace are the same command",
          "failed 3 times" in run(d, FAIL, " go test ./... "))

with tempfile.TemporaryDirectory() as d:
    run(d, FAIL, "x", session="a"); run(d, FAIL, "x", session="a")
    check("sessions do not share a streak", run(d, FAIL, "x", session="b") == "")
    check("a session id that is not a safe file name is still handled, inside the state dir",
          run(d, FAIL, "x", session="../../etc/passwd") == ""
          and all(p.parent == Path(d) for p in Path(d).iterdir())
          and not Path(d).parent.joinpath("etc").exists(), str(list(Path(d).iterdir())))

with tempfile.TemporaryDirectory() as d:
    for _ in range(2):
        run(d, FAIL, "sleep 99")
    check("an interrupted command is the user's choice, not a failure",
          run(d, FAIL, "sleep 99", is_interrupt=True) == ""
          and run(d, FAIL, "sleep 99", error="Command was interrupted by user") == "")

with tempfile.TemporaryDirectory() as d:
    for tool, cmd in (("Edit", "x"), ("Bash", ""), ("Bash", None), ("Bash", 5)):
        payload = {"hook_event_name": FAIL, "tool_name": tool, "session_id": "s",
                   "tool_input": {"command": cmd}}
        r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                           env=dict(os.environ, LEARN_ON_FAILURE_STATE=d),
                           capture_output=True, text=True)
        check(f"ignored without error: tool={tool} command={cmd!r}",
              r.returncode == 0 and r.stdout == "")
    for junk in ("", "not json", "[]", '{"tool_name": "Bash"}', "x" * 2_000_000):
        r = subprocess.run([sys.executable, str(HOOK)], input=junk,
                           env=dict(os.environ, LEARN_ON_FAILURE_STATE=d),
                           capture_output=True, text=True)
        check(f"junk on stdin exits 0 in silence ({junk[:12]!r}…)",
              r.returncode == 0 and r.stdout == "" and "Traceback" not in r.stderr, r.stderr[-120:])
    Path(d, "streak-s9.json").write_text("{corrupt")
    check("a corrupt state file is treated as no streak",
          run(d, FAIL, "x", session="s9") == "")

WRAP = ('for b in bash /bin/bash /usr/bin/bash; do command -v "$b" >/dev/null 2>&1 && export X=1 '
        '&& exec "$b" /opt/tool/launcher.sh /opt/tool/compress.py ls /nope; done; ls /nope')
check("a launcher prefix added by another hook is stripped: the real command is what counts",
      fs.unwrap(WRAP) == "ls /nope")
with tempfile.TemporaryDirectory() as d:
    run(d, FAIL, WRAP); run(d, FAIL, "ls /nope")
    out = run(d, FAIL, WRAP)
    check("...so wrapped and unwrapped runs are one streak, and the note quotes the real command",
          "failed 3 times" in out and "`ls /nope`" in out and "launcher" not in out, out[:200])
for plain in ("for f in *.txt; do wc -l \"$f\"; done; echo finished",
              "for i in 1 2 3; do echo $i; done", "ls; done; x", "make build"):
    check(f"an ordinary command is left alone: {plain[:28]}", fs.unwrap(plain) == plain)

# State must never be written through a link someone else planted.
if hasattr(os, "symlink"):
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as elsewhere:
        victim = Path(elsewhere, "victim.txt")
        victim.write_text("untouched")
        os.symlink(victim, Path(d, "streak-s1.json"))
        for _ in range(3):
            run(d, FAIL, "x")
        check("a link planted at the state file's name is not followed",
              victim.read_text() == "untouched", victim.read_text()[:60])
        check("...and the link is replaced by a real file, so counting still works",
              not Path(d, "streak-s1.json").is_symlink()
              and "failed 3 times" in run(d, FAIL, "y") + run(d, FAIL, "y") + run(d, FAIL, "y"))
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as elsewhere:
        link = Path(d, "state")
        os.symlink(elsewhere, link)
        outs = [run(str(link), FAIL, "x") for _ in range(4)]
        check("a link where the state directory should be: no state is kept, nothing is written there",
              outs == ["", "", "", ""] and list(Path(elsewhere).iterdir()) == [], str(outs))
    with tempfile.TemporaryDirectory() as d:
        for _ in range(3):
            run(d, FAIL, "x")
        modes = {oct(p.stat().st_mode & 0o777) for p in Path(d).iterdir()}
        check("state files are readable by their owner only, and no temp file is left behind",
              modes == {"0o600"} and not [p for p in Path(d).iterdir() if p.name.endswith(".tmp")], str(modes))
    with tempfile.TemporaryDirectory() as d:
        old = Path(d, "streak-old.json")
        old.write_text('{"key": "", "n": 0}')
        os.utime(old, (1, 1))
        run(d, FAIL, "x", session="fresh")
        check("streak files from long-ended sessions are pruned",
              not old.exists() and Path(d, "streak-fresh.json").exists())
check("the default state directory is under the user's home, not the shared temp directory",
      str(fs._root()).startswith(str(Path.home())) or "LEARN_ON_FAILURE_STATE" in os.environ,
      str(fs._root()))

long_cmd = "echo " + "a" * 500 + "\x1b[2J\nsecond line"
text = fs.note(long_cmd, 3)
check("a long command is cut and stripped of control characters in the note",
      "\x1b" not in text and "\n" not in text and "…" in text and len(text) < 520, str(len(text)))
check("decide() is pure: same input, same answer",
      fs.decide({"key": "", "n": 0}, FAIL, "x") == fs.decide({"key": "", "n": 0}, FAIL, "x"))

print()
if failed:
    print(f"  {len(failed)} FAILED")
    for f in failed:
        print(f"    - {f}")
    raise SystemExit(1)
print("  ALL GREEN")
