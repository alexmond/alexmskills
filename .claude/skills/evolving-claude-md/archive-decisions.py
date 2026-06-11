#!/usr/bin/env python3
"""Quarterly archive: move CLAUDE.md Decisions & Learnings entries older than
a cutoff date out into docs/decisions/{YYYY-QN}.md, leaving a single
one-line teaser behind.

Usage:
    scripts/archive-decisions.py --cutoff 2026-03-31           # dry-run preview
    scripts/archive-decisions.py --cutoff 2026-03-31 --apply   # do it

The cutoff is inclusive — entries with date <= cutoff get archived.

Mechanism:
  - Parses the D&L section out of CLAUDE.md
  - Splits entries into "to-archive" (≤ cutoff) and "keep"
  - Writes `docs/decisions/{YYYY-QN}.md` with the archived entries
  - Replaces them in CLAUDE.md with a single teaser line:
        - YYYY-QN — N entries archived → docs/decisions/YYYY-QN.md
  - Preserves strikethrough / graduation markers in the archive
  - Atomic: tmp file + rename, only on --apply
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys

CLAUDE_MD = "CLAUDE.md"
DECISIONS_DIR = "docs/decisions"
SECTION_RE = re.compile(
    r"(### Decisions & Learnings[^\n]*\n)(.*?)(?=\n### |\Z)",
    re.DOTALL,
)
ENTRY_RE = re.compile(
    r"^- (?:~~)?(\d{4}-\d{2}-\d{2})(?:~~)? — .*?(?=\n- (?:~~)?\d{4}-\d{2}-\d{2}|\Z)",
    re.MULTILINE | re.DOTALL,
)


def quarter_for(date: dt.date) -> str:
    q = (date.month - 1) // 3 + 1
    return f"{date.year}-Q{q}"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--cutoff", required=True, help="YYYY-MM-DD; entries ≤ this date are archived")
    p.add_argument("--apply", action="store_true", help="write changes (default: dry-run preview)")
    args = p.parse_args()

    try:
        cutoff = dt.date.fromisoformat(args.cutoff)
    except ValueError:
        print(f"bad --cutoff '{args.cutoff}' (need YYYY-MM-DD)", file=sys.stderr)
        return 2

    if not os.path.exists(CLAUDE_MD):
        print(f"no {CLAUDE_MD} in cwd", file=sys.stderr)
        return 2

    with open(CLAUDE_MD) as f:
        text = f.read()

    m = SECTION_RE.search(text)
    if not m:
        print("no Decisions & Learnings section found", file=sys.stderr)
        return 2
    section_heading = m.group(1)
    section_body = m.group(2)

    entries = ENTRY_RE.findall(section_body)
    if not entries:
        print("no entries to archive")
        return 0

    # Split each match back into (date, full-block).
    matches = list(ENTRY_RE.finditer(section_body))
    to_archive: list[str] = []
    to_keep: list[str] = []
    for mm in matches:
        date = dt.date.fromisoformat(mm.group(1))
        block = mm.group(0).rstrip()
        if date <= cutoff:
            to_archive.append(block)
        else:
            to_keep.append(block)

    if not to_archive:
        print(f"nothing to archive (cutoff {cutoff})")
        return 0

    # Group archived entries by quarter (most archives target one quarter, but
    # if the cutoff straddles a quarter boundary we split cleanly).
    by_quarter: dict[str, list[str]] = {}
    for block in to_archive:
        d = dt.date.fromisoformat(ENTRY_RE.match(block).group(1))
        q = quarter_for(d)
        by_quarter.setdefault(q, []).append(block)

    print(f"archive plan (cutoff {cutoff}):")
    for q, blocks in by_quarter.items():
        print(f"  {q}: {len(blocks)} entries → {DECISIONS_DIR}/{q}.md")
    print(f"  keep in CLAUDE.md: {len(to_keep)} entries")

    if not args.apply:
        print("\n(dry-run; pass --apply to write)")
        return 0

    os.makedirs(DECISIONS_DIR, exist_ok=True)

    # Write per-quarter archive files (append-mode if file exists; preserves
    # entries from earlier archive runs).
    for q, blocks in by_quarter.items():
        archive_path = os.path.join(DECISIONS_DIR, f"{q}.md")
        existed = os.path.exists(archive_path)
        with open(archive_path, "a") as f:
            if not existed:
                f.write(f"# Archived Decisions & Learnings — {q}\n\n")
                f.write(f"Entries moved out of CLAUDE.md during quarterly archive.\n\n")
            for block in blocks:
                f.write(block + "\n")
        print(f"  wrote {len(blocks)} entries to {archive_path}")

    # Rebuild the D&L section: kept entries + teaser per archived quarter.
    new_body_lines: list[str] = []
    if to_keep:
        new_body_lines.extend(b + "\n" for b in to_keep)
    for q, blocks in by_quarter.items():
        teaser = f"- {q} — **archived** — {len(blocks)} entries → {DECISIONS_DIR}/{q}.md.\n"
        new_body_lines.append(teaser)

    new_section_body = "\n" + "".join(new_body_lines)
    new_text = text[: m.start()] + section_heading + new_section_body + text[m.end():]

    tmp = CLAUDE_MD + ".tmp"
    with open(tmp, "w") as f:
        f.write(new_text)
    os.replace(tmp, CLAUDE_MD)
    print(f"  rewrote {CLAUDE_MD} (kept {len(to_keep)}, teasers {len(by_quarter)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
