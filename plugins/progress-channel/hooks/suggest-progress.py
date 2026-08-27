#!/usr/bin/env python3
"""PreToolUse advisory hook: suggest tracking a Bash command that will be
long-running. Advisory by design — hooks can't reliably rewrite a command,
so nothing is silently wrapped; the agent gets a one-line nudge.

Two signals, checked in order:
 1. The channel's own history: a prior `run --name <cmd-shape>` with a
    median over the threshold — the learned answer to "should this be
    tracked". This is the loop the design wanted: the forecast decides.
 2. A short static list of famously long-running commands, backgrounded
    commands included.

Silent on everything else. Never blocks (always exit 0)."""
from __future__ import annotations

import importlib.util
import json
import re
import statistics
import sys
from pathlib import Path

THRESHOLD_S = 10.0
LONG_RUNNERS = re.compile(
    r"^(mvn|mvnw|gradle|gradlew|make|cargo|npm|pnpm|yarn|docker|podman|"
    r"rsync|ffmpeg|tar|zstd|pytest|tox|helm|kubectl|terraform|ansible)\b"
    r"|(\bbuild\b|\bcompile\b|\bmigrate\b|\bbackup\b)")
SHORT_SAFE = re.compile(r"^(git|ls|cat|grep|rg|find|echo|which|head|tail|jq)\b")


def cmd_shape(command: str) -> str:
    """First two tokens, flags dropped — the `run --name` convention."""
    toks = [t for t in command.strip().split() if not t.startswith("-")]
    return " ".join(toks[:2])


def history_median(shape: str) -> float | None:
    spec = importlib.util.spec_from_file_location(
        "progress",
        Path(__file__).resolve().parent.parent / "scripts" / "progress.py")
    progress = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(progress)
    secs = [r["seconds"] for r in progress.load_history()
            if r.get("name") == shape and r.get("status") == "done"
            and r.get("seconds")]
    return statistics.median(secs) if secs else None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    tin = payload.get("tool_input") or {}
    command = (tin.get("command") or "").strip()
    if not command or SHORT_SAFE.match(command) or "progress.py" in command:
        return 0

    shape = cmd_shape(command)
    reason = None
    med = history_median(shape)
    if med is not None and med > THRESHOLD_S:
        reason = f"'{shape}' has a tracked history (median {int(med)}s)"
    elif tin.get("run_in_background") or LONG_RUNNERS.search(command):
        reason = "this looks long-running"

    if reason:
        plugin = Path(__file__).resolve().parent.parent
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "additionalContext": (
                f"[progress-channel] {reason} — consider registering it in "
                f"the progress channel so it is visible on the live page: "
                f"wrap it as `python3 {plugin}/scripts/progress.py run "
                f"--name '{shape}' -- <cmd>`, or use start/step/finish for "
                f"loops. Don't re-poll progress later; the channel is the "
                f"answer.")}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
