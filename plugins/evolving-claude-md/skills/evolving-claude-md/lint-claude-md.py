#!/usr/bin/env python3
"""PreToolUse hook that lints new Decisions & Learnings entries before they land
in CLAUDE.md.

Reads the Write/Edit tool input on stdin, extracts new entry lines that look
like D&L additions, and validates each against the format contract:

    - YYYY-MM-DD — **topic-tag** — body. Why: reason.

Rules enforced:
  - Valid YYYY-MM-DD date prefix
  - **topic-tag** in bold + kebab-case (lowercase letters, hyphens)
  - Body ≤ 200 chars (the part after the date+topic)

If any new entry violates, emits JSON with permissionDecision="deny" and a
reason string. The assistant retries with a corrected entry.

When the edit doesn't touch CLAUDE.md, or doesn't add any D&L-shaped line, the
hook exits silently (allow).
"""
from __future__ import annotations

import json
import os
import re
import sys

MAX_BODY_CHARS = 200
ENTRY_RE = re.compile(
    r"^- (?:~~)?(\d{4}-\d{2}-\d{2})(?:~~)? — (.*)$"
)
TOPIC_RE = re.compile(r"^\*\*([a-z][a-z0-9-]*)\*\* — (.+)$")


def is_claude_md(path: str) -> bool:
    base = os.path.basename(path)
    return base == "CLAUDE.md"


def extract_added_lines(payload: dict) -> list[str]:
    """Pull lines that this edit will ADD to CLAUDE.md — i.e., lines in
    new_string that aren't already in old_string. Pre-existing lines are
    grandfathered; only true additions get linted."""
    tool = payload.get("tool_name", "")
    inp = payload.get("tool_input", {}) or {}
    path = inp.get("file_path") or inp.get("filePath") or ""
    if not is_claude_md(path):
        return []
    if tool == "Write":
        # Full rewrite: lint everything (no old_string to diff against).
        content = inp.get("content", "") or ""
        return content.splitlines()
    if tool == "Edit":
        new = inp.get("new_string") or inp.get("newString") or ""
        old = inp.get("old_string") or inp.get("oldString") or ""
        old_lines = set(old.splitlines())
        return [ln for ln in new.splitlines() if ln not in old_lines]
    return []


def lint_line(line: str) -> str | None:
    """Return an error message if the line is a malformed D&L entry, else None.
    Non-entry lines (anything not starting with `- ` + date) pass silently."""
    m = ENTRY_RE.match(line)
    if not m:
        return None
    date, rest = m.group(1), m.group(2)
    if not (1900 < int(date[:4]) < 2200):
        return f"date {date} looks bogus"
    tm = TOPIC_RE.match(rest)
    if not tm:
        return (
            f'missing required **topic-tag** in entry: "{line[:80]}…". '
            f"Expected `- {date} — **topic-tag** — body. Why: reason.`"
        )
    body = tm.group(2)
    if len(body) > MAX_BODY_CHARS:
        return (
            f"entry body is {len(body)} chars (cap {MAX_BODY_CHARS}). "
            f"Move detail to docs/decisions/{date}-<topic>.md and keep a one-line teaser. "
            f'Entry: "{line[:80]}…"'
        )
    return None


def main() -> int:
    raw = sys.stdin.read() or "{}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return 0  # bad payload → don't block

    added = extract_added_lines(payload)
    if not added:
        return 0

    errors: list[str] = []
    for line in added:
        err = lint_line(line)
        if err:
            errors.append(err)

    if not errors:
        return 0

    msg = (
        "CLAUDE.md lint failed:\n  · "
        + "\n  · ".join(errors[:3])
        + ("\n  · …(+more)" if len(errors) > 3 else "")
        + "\n\nFormat: `- YYYY-MM-DD — **topic-tag** — body ≤200 chars. Why: reason.`"
        + "\nMove longer details to docs/decisions/{date}-{topic}.md and link from the entry."
    )

    decision = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": msg,
        }
    }
    json.dump(decision, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
