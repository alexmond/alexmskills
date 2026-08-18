---
name: memory-hygiene
description: Keep agent-written memory files from rotting. Audits ~/.claude/projects/<slug>/memory/ for facts the tree now contradicts — stale version pins, passed sequence facts, vanished paths — plus MEMORY.md index drift, and enforces the memory format contract at write time. Use when the user says "audit my memory", "memory is stale", "clean up agent memory", when a session recalls something that turns out false, or proactively when the SessionStart banner reports rot candidates.
---

# memory-hygiene

`CLAUDE.md` has `evolving-claude-md`; this governs the *other* half of the
context loaded every session — the per-project memory directory the agent
writes largely unsupervised. The failure modes differ, and that difference is
the whole design: **bloat makes an agent ignore instructions; rot makes it
confidently recall something false.** So where the sibling prunes down, this
one re-verifies and invalidates.

| | evolving-claude-md | memory-hygiene |
|---|---|---|
| Governs | `CLAUDE.md` + companions (repo-scoped, committed) | `~/.claude/projects/<slug>/memory/` (user-global, personal) |
| Author | human, agent proposes | agent, mostly unsupervised |
| Failure mode | bloat → ignored | rot → confident wrong recall |
| Pressure | prune down | re-verify / invalidate |

Both vendor the same `freshness.py` core, so "is this fact still true on
disk?" has exactly one implementation.

## What the sweep checks (all grounded, nothing pattern-only)

The `SessionStart` hook runs `audit-memory.py` against the current repo's
memory dir. Silent when healthy; otherwise a `📇` banner lists rot candidates:

- **Vanished artifact** — a backticked path/class/flag `git grep` can no
  longer find, and that isn't a path on disk. Memory-specific filters first:
  `--flags`, `<placeholders>`, `...`-abbreviated paths, and paths rooted
  outside this tree (`infra/secrets.md` cited from another repo is a pointer,
  not rot *here*) are never checked. Flagged at ≥2 missing tokens per file
  (`min_missing_artifacts`).
- **Stale version pin** — memory states `jhelm 1.3.1`, `pom.xml` now says
  `1.5.0`. Fires only when *every* parseable build-file spec contradicts the
  claim; release lines (`4.1.x`), examples, and struck-through lines stay
  silent.
- **Stale sequence fact** — "latest is `V27`" once `V28__*.sql` exists.
- **Index drift, both directions** — `MEMORY.md` lines pointing at files that
  no longer exist, and memory files with no index line (invisible to recall).

Run it on demand for the full list:

```bash
python3 <plugin>/skills/memory-hygiene/audit-memory.py [repo] --report
python3 <plugin>/skills/memory-hygiene/audit-memory.py [repo] --json
```

## What to do with a flag: supersede, never delete

A flag is a re-verification request, not a verdict. Check the fact against
the tree; if it is genuinely wrong, **strike it through and append a dated
correction** in the same file:

```markdown
~~jhelm REST embedding pins jhelm 1.3.1~~
**Correction (2026-08-18):** kweblens now builds against jhelm 1.5.0; the
1.3.1 workaround below no longer applies, kept for the reasoning.
```

Never silently delete: a memory that keeps the wrong conclusion but loses the
reasoning leads to confident re-emission, while an absent memory at least
leads to abstention. The struck line is also what keeps the auditor quiet —
`~~…~~` lines are skipped on the next sweep.

Two flag classes are known residuals — dismiss them without guilt, they are
the price of grounded checks: a memory *prescribing* files for other repos
("every graduated repo gets `checkstyle.xml`"), and a pointer file whose
bare filenames live in a sister repo. Both read instantly as fine to a human.

## The write contract (PreToolUse hook)

Location is the contract — the mechanism that held where prose instructions
failed. The hook denies, with the reason, any memory write that breaks it:

- **Fact files** (`memory/*.md`) must open with frontmatter carrying a
  kebab-case `name:`, a one-line `description:`, and `metadata.type` in
  `user | feedback | project | reference`. Added prose must not use relative
  dates ("last week" expires silently — write `2026-08-11`).
- **`MEMORY.md`** stays an index: `- [Title](file.md) — hook` lines,
  headings, blanks. Frontmatter or paragraph prose there is memory content
  in the wrong territory; move it to a fact file.

Writes anywhere outside a memory dir are never touched.

## Config

Defaults → `~/.claude/memory-hygiene/config.json` → `<repo>/.claude/memory-hygiene/config.json`;
a corrupt file is ignored, never fatal to a session start.

| Key | Default | Meaning |
|---|---|---|
| `min_missing_artifacts` | 2 | vanished tokens per file before it flags |
| `time_budget_s` | 2.5 | wall-clock cap on all grounding checks |
| `max_report` | 5 | items shown in the session banner |

## Learning loop

A false positive (a flag dismissed as fine) is more urgent than a miss — a
noisy auditor gets ignored wholesale, which re-opens the rot it exists to
close. Record both in the consuming repo's `.claude/memory-hygiene/log.md`
with the date, the evidence, and the tuning applied; recurring FP classes
graduate into a filter in `audit-memory.py` (that is how the `--flag`,
placeholder, ellipsis, and out-of-tree filters got there — each one is a
calibration scar, not a guess).
