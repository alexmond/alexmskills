#!/usr/bin/env python3
"""Audit CLAUDE.md for bloat AND staleness and emit a recommendation as
SessionStart additionalContext.

Wired as a SessionStart hook via .claude/settings.json. Silent only when the
file is healthy on every dimension; emits JSON with
`hookSpecificOutput.additionalContext` when one of the thresholds is crossed:

  - whole-file size > T_FILE_WARN / T_FILE_RECOMMEND_KB
    (the actual context-pressure dimension; D&L line/entry counts don't see
    bloat that lives under Conventions / Architecture / Gotchas / etc.)
  - D&L section line count > T_LINES_WARN / T_LINES_RECOMMEND
  - D&L entry count > T_ENTRIES_WARN / T_ENTRIES_RECOMMEND
  - any entry body > T_MEGA_ENTRY_CHARS (split or collapse candidate)
  - any leading-bold "topic" tag appears in 3+ entries (collapse candidate)
  - any entry cites a backticked artifact (path / class / flag) that doesn't
    exist in the tree (`git grep -qF` miss) → staleness candidate

When the `### Decisions & Learnings` heading is missing, the script does NOT
exit silently anymore — it reports the whole-file size + total dated-bullet
count so projects without the wiring still get a nudge.

Designed to be re-runnable manually:

    python3 scripts/audit-claude-md.py

Prints the JSON recommendation to stdout if anything is flagged; exits 0
either way so a noisy session is never blocked.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from collections import Counter

CLAUDE_MD = "CLAUDE.md"
SECTION_HEADING = "### Decisions & Learnings"

# Thresholds — calibrated 2026-06-26.
# Whole-file size is the dimension that actually correlates with harness
# context pressure; the D&L counters only see one slice of the file.
T_FILE_WARN_KB = 25
T_FILE_RECOMMEND_KB = 40
T_LINES_WARN = 200
T_LINES_RECOMMEND = 300
T_ENTRIES_WARN = 25
T_ENTRIES_RECOMMEND = 35
T_MEGA_ENTRY_CHARS = 800
T_TOPIC_CLUSTER = 3

# Staleness check — what counts as an artifact token worth checking against the
# tree. Lean conservative (high precision) so false positives don't drown the
# signal. Skip URLs, prose-y words, plain numbers, language keywords, and
# anything < 4 chars.
ARTIFACT_RE = re.compile(r"`([^`\n]{1,80})`")
ARTIFACT_LOOKS_REAL = re.compile(
    r"^(?:"
    r"[A-Za-z_][\w./\-]*\.(?:java|kt|py|ts|tsx|js|jsx|go|rs|rb|sh|sql|yml|yaml|json|toml|xml|md|adoc|html|css|scss)$"  # filenames
    r"|[A-Za-z_][\w./\-]*/[\w./\-]+"  # paths with a slash
    r"|[A-Z][A-Za-z0-9]*\.[A-Za-z][\w]*"  # ClassName.method or ClassName.FIELD
    r"|--[a-z][a-z0-9-]+"  # --cli-flags
    r"|<[a-z][a-z0-9-]+>"  # <xml-tags>
    r")$"
)
STALENESS_MIN_MISSING = 2  # entry flagged only when ≥2 of its artifact tokens are missing
STALENESS_MAX_REPORT = 5
STALENESS_TIME_BUDGET_S = 2.5  # total wall-clock cap on all git-grep checks


def looks_like_artifact(tok: str) -> bool:
    tok = tok.strip()
    if len(tok) < 4 or len(tok) > 80:
        return False
    if tok.startswith(("http://", "https://", "git@", "//")):
        return False
    return bool(ARTIFACT_LOOKS_REAL.match(tok))


def git_grep_misses(tokens: list[str]) -> list[str]:
    """Return the subset of tokens that don't appear anywhere in the tracked
    tree. Cheap: one `git grep -qF` per token; bails out (returns []) if not
    in a git repo or git is missing."""
    misses: list[str] = []
    for tok in tokens:
        try:
            r = subprocess.run(
                ["git", "grep", "-qF", "--", tok],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []
        if r.returncode == 1:  # not found
            misses.append(tok)
        elif r.returncode not in (0, 1):  # not a git repo or other error
            return []
    return misses


def main() -> int:
    if not os.path.exists(CLAUDE_MD):
        return 0

    with open(CLAUDE_MD) as f:
        text = f.read()
    file_kb = len(text.encode("utf-8")) / 1024.0

    parts: list[str] = []

    idx = text.find(SECTION_HEADING)
    if idx == -1:
        # No D&L wiring. Still report file size + total dated bullets so
        # bloat doesn't grow unwatched (the old script returned silently).
        dated_bullets = len(
            re.findall(r"^- (?:~~)?\d{4}-\d{2}-\d{2}", text, re.MULTILINE)
        )
        if file_kb < T_FILE_WARN_KB and dated_bullets < T_ENTRIES_WARN:
            return 0
        parts.append(
            f"📝 CLAUDE.md audit: no `{SECTION_HEADING}` section found "
            f"({file_kb:.1f} KB, {dated_bullets} dated bullets elsewhere)."
        )
        if file_kb > T_FILE_RECOMMEND_KB:
            parts.append("**Whole-file compaction RECOMMENDED.**")
        elif file_kb > T_FILE_WARN_KB:
            parts.append("Consider compacting the file.")
        parts.append(
            "Wire `evolving-claude-md` (add to `enabledPlugins`) so the file "
            "gets a learning loop instead of growing under one big section."
        )
        out = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": " ".join(parts),
            }
        }
        json.dump(out, sys.stdout)
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

    # Staleness check: per entry, pull backticked artifact-looking tokens and
    # ask git whether they still exist anywhere in the tree. Budget-capped so
    # the hook stays under its 5s timeout even on big files.
    stale: list[tuple[str, str, list[str]]] = []
    deadline = time.monotonic() + STALENESS_TIME_BUDGET_S
    # Newest entries first — they're the most actionable.
    for date, body in reversed(entries):
        if time.monotonic() > deadline:
            break
        toks = [t for t in ARTIFACT_RE.findall(body) if looks_like_artifact(t)]
        toks = list(dict.fromkeys(toks))  # dedup, preserve order
        if not toks:
            continue
        miss = git_grep_misses(toks)
        if len(miss) >= STALENESS_MIN_MISSING:
            m = re.match(r"\*\*([^*]+?)\*\*", body)
            hint = m.group(1).strip() if m else body.strip()[:60]
            stale.append((date, hint, miss))
        if len(stale) >= STALENESS_MAX_REPORT * 3:
            break

    level: str | None = None
    if (
        file_kb > T_FILE_RECOMMEND_KB
        or section_lines > T_LINES_RECOMMEND
        or entry_count > T_ENTRIES_RECOMMEND
    ):
        level = "recommended"
    elif (
        file_kb > T_FILE_WARN_KB
        or section_lines > T_LINES_WARN
        or entry_count > T_ENTRIES_WARN
    ):
        level = "consider"

    if not level and not mega and not clusters and not stale:
        return 0

    parts.append(
        f"📝 CLAUDE.md audit ({file_kb:.1f} KB total; {entry_count} entries, "
        f"{section_lines} lines in Decisions & Learnings)."
    )
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
    if stale:
        listed = "; ".join(
            f'{d} "{h}" cites missing {", ".join(f"`{m}`" for m in miss[:3])}'
            for d, h, miss in stale[:STALENESS_MAX_REPORT]
        )
        more = f" (+{len(stale) - STALENESS_MAX_REPORT} more)" if len(stale) > STALENESS_MAX_REPORT else ""
        parts.append(
            f"⚠️ {len(stale)} entr{'y' if len(stale) == 1 else 'ies'} cite vanished artifacts "
            f"(strike/update candidates): {listed}{more}."
        )

    parts.append(
        "When work allows, briefly propose a compaction edit to the user — graduate stable topics to Conventions/Gotchas (per skill), split mega-entries (>200 chars body) into docs/decisions/{date}-{topic}.md teasers, strike-through superseded items, and review the staleness candidates (the cited token isn't in the tree — entry may be wrong now). End-of-quarter? Suggest `scripts/archive-decisions.py --cutoff …`."
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
