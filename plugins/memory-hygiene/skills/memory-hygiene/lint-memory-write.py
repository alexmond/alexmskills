#!/usr/bin/env python3
"""PreToolUse hook that enforces the memory format contract at write time.

Location IS the contract — the one mechanism that has held where prose
instructions failed. Two territories, two rules:

  memory/*.md (a fact file) — must carry frontmatter with `name:`,
    `description:`, and `metadata.type` in {user, feedback, project,
    reference}; added prose must not use relative dates ("yesterday",
    "last week") that expire silently.

  memory/MEMORY.md (the loaded index) — stays an index: one-line
    `- [Title](file.md) — hook` pointers, headings, and blanks only.
    Frontmatter or paragraph prose in the index is memory content in the
    wrong territory; it belongs in a fact file.

Anything outside a memory dir passes untouched. Malformed payloads pass —
this hook must never block a session on its own bug.
"""
from __future__ import annotations

import json
import os
import re
import sys

MEMORY_TYPES = {"user", "feedback", "project", "reference"}
# "(the|this|that) last week" is a noun phrase, not a relative date — the
# lookbehind keeps duration prose out (found by the harness's own FP case).
RELATIVE_DATE = re.compile(
    r"\b(?:yesterday|tomorrow|(?<!the )(?<!this )(?<!that )(?:last|next) (?:week|month|year)|"
    r"a few (?:days|weeks) ago|earlier today|later today)\b", re.I)
INDEX_LINE_OK = re.compile(r"^(?:#{1,6} .*|- \[[^\]]+\]\([^)]+\.md\).*|\s*)$")


def memory_part(path: str) -> str | None:
    """Return 'index' | 'fact' when the path is inside a .claude/projects
    memory dir, else None."""
    norm = os.path.abspath(path).replace(os.sep, "/")
    m = re.search(r"/\.claude/projects/[^/]+/memory/([^/]+)$", norm)
    if not m:
        return None
    return "index" if m.group(1) == "MEMORY.md" else "fact"


def added_lines(payload: dict) -> tuple[str | None, str, list[str]]:
    tool = payload.get("tool_name", "")
    inp = payload.get("tool_input", {}) or {}
    path = inp.get("file_path") or inp.get("filePath") or ""
    part = memory_part(path) if path else None
    if part is None:
        return None, "", []
    if tool == "Write":
        content = inp.get("content", "") or ""
        return part, content, content.splitlines()
    if tool == "Edit":
        new = inp.get("new_string") or inp.get("newString") or ""
        old = inp.get("old_string") or inp.get("oldString") or ""
        old_lines = set(old.splitlines())
        return part, "", [ln for ln in new.splitlines() if ln not in old_lines]
    return None, "", []


def check_fact_frontmatter(content: str) -> list[str]:
    """Full-content checks — only possible on Write (full file in hand)."""
    errors = []
    if not content.startswith("---\n"):
        return ["memory file must start with `---` frontmatter "
                "(name, description, metadata.type)"]
    head = content.split("---", 2)[1] if content.count("---") >= 2 else ""
    if not re.search(r"^name:\s*[a-z0-9]+(?:-[a-z0-9]+)*\s*$", head, re.M):
        errors.append("frontmatter needs `name:` as a kebab-case slug")
    if not re.search(r"^description:\s*\S", head, re.M):
        errors.append("frontmatter needs a one-line `description:`")
    tm = re.search(r"^\s*type:\s*(\S+)", head, re.M)
    if not tm or tm.group(1) not in MEMORY_TYPES:
        errors.append("frontmatter needs `metadata.type` — one of user | feedback | project | reference")
    return errors


def main() -> int:
    raw = sys.stdin.read() or "{}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return 0

    part, full_content, added = added_lines(payload)
    if part is None:
        return 0

    errors: list[str] = []
    if part == "index":
        bad = [ln for ln in added if not INDEX_LINE_OK.match(ln)]
        if bad:
            errors.append(
                "MEMORY.md is the loaded index — one-line `- [Title](file.md) — hook` "
                f"pointers only. Memory content belongs in its own fact file. Offending: \"{bad[0][:70]}\""
            )
    else:
        if full_content:  # Write: whole file is in hand
            errors.extend(check_fact_frontmatter(full_content))
        rel = [ln for ln in added if RELATIVE_DATE.search(ln)]
        if rel:
            errors.append(
                "relative dates expire silently — convert to absolute YYYY-MM-DD. "
                f"Offending: \"{rel[0][:70]}\""
            )

    if not errors:
        return 0

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason":
                "memory-hygiene lint failed:\n  · " + "\n  · ".join(errors[:3]),
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
