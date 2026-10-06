#!/usr/bin/env python3
"""PostToolUse / PostToolUseFailure hook: notice a command failing in a loop.

When the same Bash command fails three times in a row, the fourth run is
unlikely to go differently. This adds one line of context saying so, so the
next step is a change of approach rather than another retry — and it marks
the moment as a multi-cycle fix, which is what this plugin exists to capture.

What it is careful about:

- Context only. It never returns a permission decision: an advisory hook has
  no business approving or blocking a command.
- It reads the failure from the event, not from the output. A failing Bash
  call arrives as PostToolUseFailure; a passing one as PostToolUse, which is
  what resets the count. No exit code is parsed out of text.
- State is a small file per session under the system temp directory — never
  inside the plugin, which is a read-only cache once installed.
- It cannot break a session: any error at all exits 0 with no output.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

THRESHOLD = 3          # failures in a row before the first note
REPEAT_EVERY = 3       # then again at 6, 9, … — a loop that ignores it once
MAX_STDIN = 1_000_000  # a hook payload is a few KB; refuse anything absurd
MAX_STATE = 4096


def _state_file(session_id: str) -> Path:
    # The session id goes into a file name, so it is reduced to a safe
    # alphabet first; anything else becomes a digest.
    safe = session_id if re.fullmatch(r"[A-Za-z0-9_-]{1,80}", session_id or "") \
        else hashlib.sha256((session_id or "").encode()).hexdigest()[:32]
    root = Path(os.environ.get("LEARN_ON_FAILURE_STATE")
                or Path(tempfile.gettempdir()) / "learn-on-failure")
    return root / f"streak-{safe}.json"


# Another plugin's PreToolUse hook may rewrite a command before it runs,
# putting a launcher loop in front of it:
#     for b in bash /bin/bash …; do … exec "$b" <launcher> <args>; done; <command>
# This hook then sees the rewritten text. Quoting the first hundred characters
# of that names the launcher, not what was run (seen in a real session). The
# original command is what follows the loop, so that is what gets counted and
# quoted. Anything not shaped exactly like this is left alone.
_LAUNCHER = re.compile(r"^\s*for\s+\w+\s+in\s+[^;]*;\s*do\s.{0,4000}?;\s*done\s*;\s*(?P<rest>\S.*)$",
                       re.S)


def unwrap(command: str) -> str:
    m = _LAUNCHER.match(command[:20000])
    return m.group("rest") if m and " exec " in command[:m.start("rest")] else command


def _key(command: str) -> str:
    """Two runs are 'the same command' when they differ only in whitespace."""
    return hashlib.sha256(" ".join(command.split()).encode()).hexdigest()[:16]


def _load(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.loads(fh.read(MAX_STATE))
        if isinstance(data, dict) and isinstance(data.get("n"), int) \
                and isinstance(data.get("key"), str):
            return data
    except (OSError, ValueError):
        pass
    return {"key": "", "n": 0}


def _save(path: Path, state: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        os.replace(tmp, path)
    except OSError:
        pass


def note(command: str, n: int) -> str:
    shown = " ".join(command.split())
    # Control characters out: this text is shown to the model and may be
    # echoed to a terminal.
    shown = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", shown)
    if len(shown) > 100:
        shown = shown[:97] + "…"
    return (
        f"[learn-on-failure] The same command has now failed {n} times in a "
        f"row: `{shown}`. Running it again is not converging. Stop and change "
        f"approach: read the error text, check the assumption the command "
        f"rests on, or take a different route. When this is resolved it was a "
        f"multi-cycle fix — save what the wrong assumption was with the "
        f"learn-on-failure skill.")


def decide(state: dict, event: str, command: str) -> tuple[dict, str]:
    """(new state, note or "") for one Bash result. Pure, so it is testable."""
    if event != "PostToolUseFailure":
        return {"key": "", "n": 0}, ""           # any success ends the streak
    key = _key(command)
    n = state["n"] + 1 if state.get("key") == key else 1
    due = n >= THRESHOLD and (n - THRESHOLD) % REPEAT_EVERY == 0
    return {"key": key, "n": n}, (note(command, n) if due else "")


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read(MAX_STDIN))
    except ValueError:
        return 0
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return 0
    event = str(payload.get("hook_event_name") or "")
    if event not in ("PostToolUse", "PostToolUseFailure"):
        return 0
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not command.strip():
        return 0
    # An interrupted command is the user's decision, not a failure to learn from.
    if payload.get("is_interrupt") or "interrupted by user" in str(payload.get("error", "")).lower():
        return 0

    command = unwrap(command)
    path = _state_file(str(payload.get("session_id") or ""))
    state, text = decide(_load(path), event, command)
    _save(path, state)
    if text:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": event, "additionalContext": text}}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        raise SystemExit(0)
