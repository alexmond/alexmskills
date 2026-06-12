#!/usr/bin/env python3
"""Audit CLAUDE.md's Decisions & Learnings section for bloat and emit a
compaction recommendation as SessionStart additionalContext.

Wired as a SessionStart hook via .claude/settings.json. Silent when the file
is healthy; emits JSON with `hookSpecificOutput.additionalContext` when one
of the thresholds is crossed:

  - section line count > T_LINES_WARN / T_LINES_RECOMMEND
  - entry count > T_ENTRIES_WARN / T_ENTRIES_RECOMMEND
  - any entry body > T_MEGA_ENTRY_CHARS (split or collapse candidate)
  - any leading-bold "topic" tag appears in 3+ entries (collapse candidate)

The hook receives an empty stdin {} from SessionStart; this script ignores
stdin and reads CLAUDE.md from CWD. Designed to be re-runnable manually:

    python3 scripts/audit-claude-md.py

Prints the JSON recommendation to stdout if anything is flagged; exits 0
either way so a noisy session is never blocked.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter

CLAUDE_MD = "CLAUDE.md"
SECTION_HEADING = "### Decisions & Learnings"

# Thresholds — tuned against this project's CLAUDE.md as of 2026-06-10.
T_LINES_WARN = 200
T_LINES_RECOMMEND = 300
T_ENTRIES_WARN = 25
T_ENTRIES_RECOMMEND = 35
T_MEGA_ENTRY_CHARS = 800
T_TOPIC_CLUSTER = 3


def main() -> int:
    if not os.path.exists(CLAUDE_MD):
        return 0

    with open(CLAUDE_MD) as f:
        text = f.read()

    idx = text.find(SECTION_HEADING)
    if idx == -1:
        return 0
    section = text[idx + len(SECTION_HEADING):]
    next_h3 = re.search(r"\n### ", section)
    if next_h3:
        section = section[: next_h3.start()]

    section_lines = section.count("\n")

    # Entries: a top-level bullet line starting with "- YYYY-MM-DD" (optionally
    # wrapped in ~~...~~ for superseded), followed by the body until the next
    # such bullet (or end of section).
    entry_pat = re.compile(
        r"^- (?:~~)?(\d{4}-\d{2}-\d{2})(?:~~)? — (.+?)(?=\n- (?:~~)?\d{4}-\d{2}-\d{2}|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    entries = entry_pat.findall(section)
    entry_count = len(entries)

    mega = [(d, b.strip()[:90]) for d, b in entries if len(b) > T_MEGA_ENTRY_CHARS]

    # Topic clustering by the first bold phrase in the body.
    topics: list[str] = []
    for _, body in entries:
        m = re.match(r"\*\*([^*]+?)\*\*", body)
        if not m:
            continue
        t = m.group(1).strip().lower()
        t = re.sub(r"[.,:;!?]+$", "", t)
        t = re.sub(r"\s*\([^)]*\)\s*$", "", t)
        topics.append(t)
    topic_freq = Counter(topics)
    clusters = sorted(
        ((t, n) for t, n in topic_freq.items() if n >= T_TOPIC_CLUSTER),
        key=lambda x: -x[1],
    )

    level: str | None = None
    if section_lines > T_LINES_RECOMMEND or entry_count > T_ENTRIES_RECOMMEND:
        level = "recommended"
    elif section_lines > T_LINES_WARN or entry_count > T_ENTRIES_WARN:
        level = "consider"

    if not level and not mega and not clusters:
        return 0

    parts = [
        f"📝 CLAUDE.md audit ({entry_count} entries, {section_lines} lines in Decisions & Learnings)."
    ]
    if level == "recommended":
        parts.append("**Compaction RECOMMENDED.**")
    elif level == "consider":
        parts.append("Consider compaction.")

    if mega:
        head = "; ".join(f'{d}: "{h}…"' for d, h in mega[:3])
        parts.append(
            f"{len(mega)} mega-entr{'y' if len(mega) == 1 else 'ies'} (>{T_MEGA_ENTRY_CHARS} chars): {head}."
        )
    if clusters:
        listed = ", ".join(f'"{t}" ({n})' for t, n in clusters[:5])
        parts.append(
            f"Topic tags with {T_TOPIC_CLUSTER}+ entries (graduation candidates → Conventions/Gotchas): {listed}."
        )

    parts.append(
        "When work allows, briefly propose a compaction edit to the user — graduate stable topics to Conventions/Gotchas (per skill), split mega-entries (>200 chars body) into docs/decisions/{date}-{topic}.md teasers, strikethrough superseded items. End-of-quarter? Suggest `scripts/archive-decisions.py --cutoff …`."
    )

    out = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": " ".join(parts),
        }
    }
    json.dump(out, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
