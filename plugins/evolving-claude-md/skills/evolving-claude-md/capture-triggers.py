#!/usr/bin/env python3
"""Capture triggers — the write path the audit never had (issue #37, #40).

Every other hook in this plugin is pruning pressure on entries that already
exist. These two are the only mechanisms that fire when the log was never
written to:

  stop    — Stop hook. If this session made commits and edited files but never
            touched CLAUDE.md (and added nothing under docs/decisions/), block
            the stop ONCE with a prompt to nominate 0-3 entries. Zero is
            explicitly allowed — filler is worse than silence.
  commit  — PostToolUse(Bash) hook. If the command was a git commit and the
            fresh commit message contains gotcha-shaped language, emit
            additionalContext suggesting the promotion while the context is
            hot — far higher yield than asking at session end.

Both ship DEFAULT-OFF and are enabled per repo (or globally) in
.claude/evolving-claude-md/config.json:

    {"capture_prompt": "session-end", "commit_mining": true}

The 59%-fire-rate lesson from the retired gotchas check applies: these stay
off until the calibration pass (#43) has measured their noise on real repos.

Routing rule carried in the prompts (one capture engine, two destinations):
repo-durable, team-relevant learnings become D&L entries; machine-personal or
private ones are saved via the learn-on-failure skill to user memory.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

CONFIG_REL = os.path.join(".claude", "evolving-claude-md", "config.json")
STATE_DIR = os.path.join(".claude", "evolving-claude-md")

DEFAULTS = {
    "capture_prompt": "off",   # "off" | "session-end"
    "commit_mining": False,
}

# Gotcha-shaped language in commit messages — each phrase is a finished
# learning that needed only a date and a tag (#37 proposal 5's examples).
GOTCHA_RE = re.compile(
    r"found the hard way|turns out|silently|reports success"
    r"|does n[o']t actually|doesn't actually|was wrong|hid behind"
    r"|root cause|the fix was|off[- ]by[- ]one|red herring",
    re.I,
)

ROUTING = (
    "Route each entry: repo-durable and team-relevant -> a D&L entry in "
    "CLAUDE.md (dated, topic-tagged, <=200 chars, lead with the why); "
    "machine-personal or private -> save via the learn-on-failure skill to "
    "user memory instead. Zero entries is a valid answer - do not invent "
    "filler."
)


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    for path in (os.path.join(os.path.expanduser("~"), CONFIG_REL), CONFIG_REL):
        try:
            with open(path) as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                cfg.update({k: v for k, v in loaded.items() if k in DEFAULTS})
        except (OSError, ValueError):
            continue
    return cfg


def _git(args: list[str]) -> str:
    try:
        r = subprocess.run(["git", *args], capture_output=True, text=True, timeout=3)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def session_activity(transcript_path: str) -> dict:
    """Stream the session transcript once; return what kind of work happened.

    Line-by-line with a byte cap so a huge transcript can't blow the hook's
    time budget — the signals we need all fit in cheap substring checks.
    """
    act = {"commits": 0, "edits": 0, "claude_md_touched": False, "decisions_added": False}
    budget = 8 * 1024 * 1024
    try:
        with open(transcript_path, errors="replace") as fh:
            for line in fh:
                budget -= len(line)
                if budget < 0:
                    break
                if '"name": "Bash"' in line or '"name":"Bash"' in line:
                    if "git commit" in line:
                        act["commits"] += 1
                elif '"name": "Edit"' in line or '"name": "Write"' in line \
                        or '"name":"Edit"' in line or '"name":"Write"' in line:
                    act["edits"] += 1
                    if "CLAUDE.md" in line:
                        act["claude_md_touched"] = True
                    if "docs/decisions/" in line:
                        act["decisions_added"] = True
    except OSError:
        pass
    return act


def run_stop(payload: dict, cfg: dict) -> int:
    if cfg.get("capture_prompt") != "session-end":
        return 0
    session_id = payload.get("session_id", "")
    transcript = payload.get("transcript_path", "")
    if not session_id or not transcript:
        return 0
    # Fire at most once per session, or the blocked stop re-triggers us forever.
    marker = os.path.join(STATE_DIR, f".capture-{session_id}")
    if os.path.exists(marker):
        return 0
    if not os.path.exists("CLAUDE.md"):
        return 0
    act = session_activity(transcript)
    if not act["commits"] or not act["edits"]:
        return 0
    if act["claude_md_touched"] or act["decisions_added"]:
        return 0
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        open(marker, "w").close()
    except OSError:
        return 0
    json.dump(
        {
            "decision": "block",
            "reason": (
                f"[evolving-claude-md capture] This session committed "
                f"{act['commits']} time(s) and edited files, but CLAUDE.md was "
                f"never touched and no docs/decisions/ file was added. Before "
                f"stopping: nominate 0-3 durable learnings from this session. "
                + ROUTING
                + " Then stop; this prompt fires once per session."
            ),
        },
        sys.stdout,
    )
    return 0


def run_commit(payload: dict, cfg: dict) -> int:
    if not cfg.get("commit_mining"):
        return 0
    command = (payload.get("tool_input") or {}).get("command", "")
    if "git commit" not in command:
        return 0
    if not os.path.exists("CLAUDE.md"):
        return 0
    msg = _git(["log", "-1", "--format=%B"])
    if not msg:
        return 0
    hits = sorted({m.group(0).lower() for m in GOTCHA_RE.finditer(msg)})
    if not hits:
        return 0
    subject = msg.strip().splitlines()[0][:70]
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": (
                    f"[evolving-claude-md capture] The commit just made "
                    f"(\"{subject}\") contains gotcha-shaped language "
                    f"({', '.join(repr(h) for h in hits[:3])}) — a finished "
                    f"learning that needs only a date and a tag. Offer to "
                    f"promote it now, while the context is hot. " + ROUTING
                ),
            }
        },
        sys.stdout,
    )
    return 0


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    cfg = load_config()
    if mode == "stop":
        return run_stop(payload, cfg)
    if mode == "commit":
        return run_commit(payload, cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
