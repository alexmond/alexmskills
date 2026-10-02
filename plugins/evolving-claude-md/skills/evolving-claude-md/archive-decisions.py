#!/usr/bin/env python3
"""Archive: move CLAUDE.md Decisions & Learnings entries older than a cutoff
date out into docs/decisions/{YYYY-QN}.md, leaving one teaser line per quarter.

Usage:
    archive-decisions.py --cutoff 2026-03-31           # dry-run preview
    archive-decisions.py --cutoff 2026-03-31 --apply   # do it

The cutoff is inclusive — entries with date <= cutoff get archived.

Mechanism:
  - Parses the D&L section out of CLAUDE.md, line by line, into blocks
  - Archives dated entries <= cutoff to `docs/decisions/{YYYY-QN}.md`
    (appending if the file exists)
  - Leaves one teaser per quarter, MERGING with a teaser an earlier run left:
        - YYYY-QN — **archived** — N entries → docs/decisions/YYYY-QN.md.
  - Everything else in the section stays where it was: the format note, other
    bullets, earlier teasers
  - Preserves strikethrough / graduation markers in the archive
  - Atomic: tmp file + rename, only on --apply

It is safe to run repeatedly with a moving cutoff, which `/evolving-claude-md:
compact` does. An earlier version rebuilt the section from dated entries only,
so it dropped the section's format note, and an entry's block ran on until the
next DATED bullet — swallowing a teaser below it into the archive, after which
the new teaser reported only the latest run's count.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys

CLAUDE_MD = os.environ.get("SKILL_INSTRUCTIONS_FILE", "CLAUDE.md")
DECISIONS_DIR = "docs/decisions"
SECTION_RE = re.compile(
    r"(### Decisions & Learnings[^\n]*\n)(.*?)(?=\n### |\Z)",
    re.DOTALL,
)
ENTRY_START = re.compile(r"^- (?:~~)?(\d{4}-\d{2}-\d{2})(?:~~)? — ")
TEASER_RE = re.compile(
    r"^- (\d{4}-Q[1-4]) — \*\*archived\*\* — (\d+) entr(?:y|ies) → (\S+?)\.?\s*$")


def quarter_for(date: dt.date) -> str:
    q = (date.month - 1) // 3 + 1
    return f"{date.year}-Q{q}"


def teaser(quarter: str, n: int) -> str:
    noun = "entry" if n == 1 else "entries"
    return f"- {quarter} — **archived** — {n} {noun} → {DECISIONS_DIR}/{quarter}.md."


def parse_blocks(body: str) -> list[dict]:
    """Split a section body into ordered blocks.

    kind: "entry" (dated bullet + its indented continuation lines), "teaser",
    or "other" (any other line, kept verbatim: the format note, blank lines,
    undated bullets). A block ends at the next top-level bullet or a blank
    line, so an entry can never absorb the line below it.
    """
    blocks: list[dict] = []
    cur: dict | None = None
    for line in body.split("\n"):
        m_entry = ENTRY_START.match(line)
        m_teaser = TEASER_RE.match(line)
        if m_entry:
            cur = {"kind": "entry", "date": m_entry.group(1), "lines": [line]}
            blocks.append(cur)
        elif m_teaser:
            cur = None
            blocks.append({"kind": "teaser", "quarter": m_teaser.group(1),
                           "n": int(m_teaser.group(2)), "lines": [line]})
        elif cur is not None and line.strip() and not line.startswith("- "):
            cur["lines"].append(line)          # continuation of the entry
        else:
            cur = None
            blocks.append({"kind": "other", "lines": [line]})
    return blocks


def plan(text: str, cutoff: dt.date):
    """Pure: returns (new_text, by_quarter{q: [entry blocks]}, kept_count) or
    None when there is no D&L section."""
    m = SECTION_RE.search(text)
    if not m:
        return None
    blocks = parse_blocks(m.group(2))
    by_quarter: dict[str, list[str]] = {}
    kept: list[dict] = []
    for b in blocks:
        if b["kind"] == "entry" and dt.date.fromisoformat(b["date"]) <= cutoff:
            by_quarter.setdefault(quarter_for(dt.date.fromisoformat(b["date"])),
                                  []).append("\n".join(b["lines"]).rstrip())
        else:
            kept.append(b)

    # Merge into teasers an earlier run left; add new ones after the last
    # kept entry, so they read as the tail of the Recent list.
    seen: set[str] = set()
    for b in kept:
        if b["kind"] == "teaser" and b["quarter"] in by_quarter:
            b["lines"] = [teaser(b["quarter"],
                                 b["n"] + len(by_quarter[b["quarter"]]))]
            seen.add(b["quarter"])
    new = [teaser(q, len(v)) for q, v in sorted(by_quarter.items(), reverse=True)
           if q not in seen]
    if new:
        last = max((i for i, b in enumerate(kept)
                    if b["kind"] in ("entry", "teaser")), default=None)
        if last is None:
            # Nothing dated left: put teasers after the leading prose/note.
            last = max((i for i, b in enumerate(kept)
                        if any(l.strip() for l in b["lines"])), default=-1)
        for j, t in enumerate(new):
            kept.insert(last + 1 + j, {"kind": "teaser", "lines": [t]})

    body = "\n".join(l for b in kept for l in b["lines"])
    new_text = text[: m.start()] + m.group(1) + body + text[m.end():]
    n_kept = sum(1 for b in kept if b["kind"] == "entry")
    return new_text, by_quarter, n_kept


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

    result = plan(text, cutoff)
    if result is None:
        print("no Decisions & Learnings section found", file=sys.stderr)
        return 2
    new_text, by_quarter, n_kept = result

    if not by_quarter:
        print(f"nothing to archive (cutoff {cutoff})")
        return 0

    print(f"archive plan (cutoff {cutoff}):")
    for q, blocks in sorted(by_quarter.items()):
        print(f"  {q}: {len(blocks)} entries → {DECISIONS_DIR}/{q}.md")
    print(f"  keep in CLAUDE.md: {n_kept} entries")

    if not args.apply:
        print("\n(dry-run; pass --apply to write)")
        return 0

    os.makedirs(DECISIONS_DIR, exist_ok=True)
    for q, blocks in sorted(by_quarter.items()):
        archive_path = os.path.join(DECISIONS_DIR, f"{q}.md")
        existed = os.path.exists(archive_path)
        with open(archive_path, "a") as f:
            if not existed:
                f.write(f"# Archived Decisions & Learnings — {q}\n\n")
                f.write("Entries moved out of CLAUDE.md by archive-decisions.py.\n\n")
            for block in blocks:
                f.write(block + "\n")
        print(f"  wrote {len(blocks)} entries to {archive_path}")

    tmp = CLAUDE_MD + ".tmp"
    with open(tmp, "w") as f:
        f.write(new_text)
    os.replace(tmp, CLAUDE_MD)
    print(f"  rewrote {CLAUDE_MD} (kept {n_kept})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
