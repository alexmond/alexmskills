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
    r"|^git\s+(clone|fetch|pull|lfs|submodule)\b"
    r"|(\bbuild\b|\bcompile\b|\bmigrate\b|\bbackup\b)")
# git is short-safe EXCEPT the network/worktree ops that can run for minutes
# on a large repo — those fall through to LONG_RUNNERS above.
SHORT_SAFE = re.compile(
    r"^git\b(?!\s+(clone|fetch|pull|lfs|submodule)\b)"
    r"|^(ls|cat|grep|rg|find|echo|which|head|tail|jq)\b")
# Tools whose own output carries [done/total] position — the tap turns that
# into a MEASURED bar, which beats the run wrapper's time estimate.
TAPPABLE = re.compile(r"^(mvn|mvnw|\S*gradlew?|make)\b|^git\s+(clone|fetch|pull)\b")
STATUSLINE_TIP_DAYS = 7.0


def cmd_shape(command: str) -> str:
    """First two tokens, flags dropped — the `run --name` convention."""
    toks = [t for t in command.strip().split() if not t.startswith("-")]
    return " ".join(toks[:2])


def _progress_mod():
    spec = importlib.util.spec_from_file_location(
        "progress",
        Path(__file__).resolve().parent.parent / "scripts" / "progress.py")
    progress = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(progress)
    return progress


def history_median(progress, shape: str) -> float | None:
    secs = [r["seconds"] for r in progress.load_history()
            if r.get("name") == shape and r.get("status") == "done"
            and r.get("seconds")]
    return statistics.median(secs) if secs else None


def statusline_tip(progress) -> str:
    """One line, at most once a week, only while a daemon is answering and no
    status-line renderer has ever polled it. The person is registering jobs
    they cannot see — this is the moment the integration matters to them."""
    import time
    marker = progress.home() / ".statusline-tipped"
    try:
        if (marker.exists()
                and time.time() - marker.stat().st_mtime
                < STATUSLINE_TIP_DAYS * 86400):
            return ""
        health = progress._get_json("/health", timeout=0.25) or {}
        if health.get("statusline_seen") is not False:
            return ""
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        return (" Tip: these bars can render live in the Claude Code status "
                "line, which is not set up — offer the user the setup "
                "(SKILL.md 'Status line' section; they can say \"set up the "
                "progress status line\").")
    except Exception:
        return ""


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

    progress = _progress_mod()
    shape = cmd_shape(command)
    reason = None
    med = history_median(progress, shape)
    if med is not None and med > THRESHOLD_S:
        reason = f"'{shape}' has a tracked history (median {int(med)}s)"
    elif tin.get("run_in_background") or LONG_RUNNERS.search(command):
        reason = "this looks long-running"

    if reason:
        plugin = Path(__file__).resolve().parent.parent
        if TAPPABLE.search(command):
            # The tool's own output carries [done/total]; the tap reads it
            # in passing and the bar is measured, not estimated. git needs
            # --progress when piped, or it prints no position at all.
            how = (f"pipe it through the tap for a measured bar: `<cmd> 2>&1 "
                   f"| python3 {plugin}/scripts/progress_tap.py '{shape}'` "
                   f"(git: add --progress and use --pattern git; read "
                   f"`${{PIPESTATUS[0]}}`, not `$?`)")
        else:
            how = (f"wrap it as `python3 {plugin}/scripts/progress.py run "
                   f"--name '{shape}' -- <cmd>`, or use start/step/finish "
                   f"for loops")
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "additionalContext": (
                f"[progress-channel] {reason} — consider registering it in "
                f"the progress channel so it is visible on the live page: "
                f"{how}. Don't re-poll progress later; the channel is the "
                f"answer." + statusline_tip(progress))}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
