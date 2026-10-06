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
import os
import re
import statistics
import sys
from pathlib import Path

THRESHOLD_S = 10.0
LONG_RUNNERS = re.compile(
    r"^(mvn|mvnw|gradle|gradlew|make|cargo|npm|pnpm|yarn|docker|podman|"
    r"rsync|ffmpeg|tar|zstd|pytest|tox|helm|kubectl|terraform|ansible|"
    r"ansible-playbook|ninja|cmake|meson|bazel|jest|vitest|xcodebuild)\b"
    # Tools with quick subcommands too (`go version`, `pip list`): only the
    # slow ones count, or the nudge fires on every other command.
    r"|^go\s+(test|build|install|generate|vet)\b"
    r"|^dotnet\s+(build|test|publish|restore|pack)\b"
    r"|^(pip3?|uv\s+pip)\s+install\b|^uv\s+sync\b|^poetry\s+install\b"
    r"|^bundle\s+install\b|^composer\s+(install|update)\b"
    r"|^mix\s+(test|compile|deps\.get)\b|^swift\s+(build|test)\b"
    r"|^bun\s+(install|test)\b"
    r"|^git\s+(clone|fetch|pull|lfs|submodule)\b"
    r"|(\bbuild\b|\bcompile\b|\bmigrate\b|\bbackup\b)")
# git is short-safe EXCEPT the network/worktree ops that can run for minutes
# on a large repo — those fall through to LONG_RUNNERS above.
SHORT_SAFE = re.compile(
    r"^git\b(?!\s+(clone|fetch|pull|lfs|submodule)\b)"
    r"|^(ls|cat|grep|rg|find|echo|which|head|tail|jq)\b")
# Which tap pattern reads which tool, and the flag (if any) the tool needs to
# print its position into a pipe at all. First match wins, so the specific
# subcommands come before the bare tool. A tool that is not here has no
# pattern, and is offered the run wrapper instead of a tap that would match
# nothing — `make` and Gradle were listed as tappable with no pattern behind
# them until 0.8.0.
TAPS = [
    (r"^(\./)?mvnw?\b", "maven", ""),
    (r"^git\s+(clone|fetch|pull)\b", "git", "add --progress"),
    (r"^(\./)?gradlew?\b", "gradle", "add --console=plain"),
    (r"^cargo\s+(build|check|test|clippy|install|run)\b", "cargo", ""),
    (r"^go\s+test\b", "go", ""),
    (r"^(python3?\s+-m\s+)?pytest\b|^tox\b|^(uv|poetry)\s+run\s+pytest\b", "pytest", ""),
    (r"^(npx\s+)?(jest|vitest)\b|^(npm|pnpm|yarn|bun)\s+(run\s+)?test\b", "jest", ""),
    (r"^(docker|podman)\s+(buildx\s+)?build\b|^docker\s+compose\s+build\b",
     "docker", "add --progress=plain"),
    (r"^ninja\b|^meson\s+compile\b|^bazel\s+(build|test)\b", "ninja", ""),
    (r"^cmake\s+--build\b|^make\b", "cmake", ""),
    (r"^dotnet\s+(build|publish|pack)\b", "dotnet", ""),
    (r"^rsync\b", "rsync", "add --info=progress2"),
    (r"^terraform\s+(apply|destroy)\b", "terraform", ""),
    (r"^ansible-playbook\b", "ansible", ""),
]


def tap_for(command: str):
    """(pattern, flag hint) for a command the tap can read, else None."""
    for rx, pattern, hint in TAPS:
        if re.search(rx, command):
            return pattern, hint
    return None
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
    if os.environ.get("SKILL_CLIENT") == "codex":
        return " Use the browser dashboard or a companion terminal running progress.py watch."
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
                "(the skill's references/in-the-window.md; they can say \"set up the "
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
        tap = tap_for(command)
        if tap:
            # The tool's own output carries its position; the tap reads it in
            # passing, so the bar is the tool's own count rather than a guess.
            # Some tools print nothing into a pipe without a flag.
            pattern, hint = tap
            flag = "" if pattern == "maven" else f" --pattern {pattern}"
            how = (f"pipe it through the tap so the bar comes from the tool's "
                   f"own output: `<cmd> 2>&1 | python3 {plugin}/scripts/"
                   f"progress_tap.py '{shape}'{flag}`"
                   + (f" ({hint} so it prints position in a pipe)" if hint else "")
                   + "; read `${PIPESTATUS[0]}`, not `$?`")
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
