#!/usr/bin/env python3
"""SessionStart hook for the senior-prompts plugin.

Two jobs, both safe and non-blocking:

  1. Init-on-install — the first time the plugin runs in a repo, create
     .claude/senior-prompts/learnings.md (the per-repo log the skills append to).
  2. Compress-when-large — when the log grows past a threshold, emit a
     compaction recommendation as SessionStart additionalContext so the
     assistant compresses it (merge duplicates, drop the now-obvious, keep the
     durable lessons). The hook never rewrites the file itself.

Reads nothing from stdin; resolves the log relative to CWD. Exits 0 always.
"""
from __future__ import annotations

import json
import os
import sys

LOG_DIR = os.path.join(".claude", "senior-prompts")
LOG = os.path.join(LOG_DIR, "learnings.md")

HEADER = """# senior-prompts — learnings (this repo)

Durable lessons surfaced while using the senior-prompts skills. One line each:
`- YYYY-MM-DD — <skill> — <lesson>`. Keep it lean — the SessionStart hook
recommends compaction when this grows; compress by merging duplicates and
dropping anything now obvious from the code.
"""

T_ENTRIES = 40
T_LINES = 200


def emit(msg: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": msg,
        }
    }))


def main() -> int:
    # 1. init-on-install
    if not os.path.exists(LOG):
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            with open(LOG, "w", encoding="utf-8") as f:
                f.write(HEADER)
        except OSError:
            pass
        return 0

    # 2. compress-when-large (recommend only)
    try:
        text = open(LOG, encoding="utf-8").read()
    except OSError:
        return 0

    entries = [ln for ln in text.splitlines() if ln.startswith("- ")]
    lines = text.count("\n") + 1
    if len(entries) > T_ENTRIES or lines > T_LINES:
        emit(
            f"senior-prompts learnings log is large ({len(entries)} entries, {lines} lines). "
            f"Compress {LOG}: merge duplicate lessons, drop anything now obvious from the code, "
            f"keep only durable reusable learnings."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
