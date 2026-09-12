---
name: evolving-claude-md
description: Set up CLAUDE.md to maintain a living Decisions & Learnings log that stays bounded as the project evolves — a format contract enforced at write time, four pruning pressures, and a coverage check for the essentials. Use when the user says "make CLAUDE.md evolve", "self-updating CLAUDE.md", "add a learning mechanism to CLAUDE.md", "decisions log", "ADR-style notes", "how do we keep CLAUDE.md current", "compact CLAUDE.md", "CLAUDE.md is getting too big" — or when a CLAUDE.md exists with no mechanism for keeping itself current. Complements (does not replace) the built-in `init` skill: `init` bootstraps the description of the codebase, this adds the mechanism that keeps it from bloating.
---

# Evolving CLAUDE.md

> **Try it:** `/evolving-claude-md:evolving-claude-md` — or say "make CLAUDE.md evolve".

CLAUDE.md is read into Claude's context on every turn. Every byte costs tokens. So the goal isn't "log everything we learned" — it's **a small, well-pruned set of durable decisions that future-Claude needs, with everything else linked to or archived**.

This skill wires that. Three mechanisms keep it healthy automatically:

| Hook | When | What it does |
|---|---|---|
| **SessionStart** | start of every session | `audit-claude-md.py` — if the D&L section is bloated, injects a recommendation to compact |
| **PreToolUse** on `Write\|Edit` of `CLAUDE.md` | before each edit | `lint-claude-md.py` — rejects new entries that violate the format (no topic tag, no date, > 200 chars) |
| **PostCompact** | after context compaction | re-runs the audit so the assistant sees the current D&L state without paying for the full file twice |

When installed as a **plugin**, the three hooks ship inside the plugin (`hooks/hooks.json`, pathed via `${CLAUDE_PLUGIN_ROOT}`) and register automatically once enabled — nothing to add to your settings. For a **manual install**, copy the three scripts to `.claude/skills/evolving-claude-md/` and add the hooks to `.claude/settings.json` (see *Setup checklist*). Disable individually by removing the entry; disable all via `disableAllHooks: true` in settings.

> Not for documenting a codebase from scratch — that's `init`. This adds the
> mechanism that keeps the file current and bounded once it exists.

## Format — the contract every entry must follow

```
- YYYY-MM-DD — **topic-tag** — short statement. Why: brief reason. [Optional: see → docs/decisions/...].
```

- **YYYY-MM-DD** — calendar date, no relative dates.
- **`**topic-tag**`** — kebab-case, one or two words, MANDATORY. Reuse existing tags where they fit; the lint hook surfaces the inventory. Pick a stable vocabulary per project (e.g. `auth`, `build`, `schema`, `ci`, `perf`).
- **One sentence of *what***. The *why* is the load-bearing half — lead with constraint, incident, or preference.
- **Hard cap: 200 chars in the body, max 3 lines.** Bigger? Move the detail to `docs/decisions/{YYYY-MM-DD}-{topic}.md` and keep the entry as a one-line teaser linking there. The lint hook enforces this.

Examples:
```
- 2026-06-10 — **build** — switched from system `mvn` to the checked-in `./mvnw`. Why: CI and dev were on different Maven versions; wrapper pins it.
- 2026-06-09 — **auth** — env API key now ignored in favour of subscription login (forceLoginMethod). Why: key value rotates; setup must survive it.
- 2026-06-08 — **schema** — `verified` flag added inline on the record. Why: downstream filter needs a trusted-only view. See → docs/decisions/2026-06-08-schema.md.
```

## What to log — the bar decides, the triggers only nominate

**The bar. Write the candidate as a sentence that is true about this repo
*tomorrow*, then name what a future session does differently knowing it.** If
the only true sentence is "we did X", there is no entry — git log, the tickets
and the changelog already hold that, and a log that repeats them stops being
read. Most sessions produce zero entries, and zero is the right answer to a
session that merely shipped.

A delivery earns an entry only when it **taught** something a reader can't see
in the code: a constraint, a trap, a reversal, a rule. "Shipped 0.4.0 with the
new estimator" is a changelog line. "The publish plugin ignores `deploy.skip`,
so skipped modules still publish" is an entry.

These six *nominate* — the bar above decides:

1. A non-trivial architectural decision (stack, schema, tradeoff resolved).
2. Durable user feedback (preferences, things to never do, validated approaches).
3. A non-obvious gotcha (build quirks, library traps, third-party API limits).
4. A convention established or revised.
5. A scope shift (something moved in/out, priorities reordered).
6. An external dependency or service added / replaced / removed.

## What NOT to log

- **A delivery.** Shipping, bumping, adding a feature — the release is not the
  learning. Measured on one repo: 63% of entries restated a version its own
  `CHANGELOG.md` already documented, which is what the audit's CHANGELOG-mirror
  check now reports.
- **Anything a durable artifact already carries.** If the repo keeps a
  changelog, ADRs or tickets, the entry is earned only by the part that isn't
  in them.
- Routine code changes ("renamed X to Y") — git log has it.
- Transient task state — the task list has it.
- Anything obvious from reading the code now.
- Duplicates of an existing convention/gotcha — update the existing entry instead.
- Mega-context dumps. If you find yourself writing >200 chars, you're writing a design doc; put the doc in `docs/decisions/` and link to it.

## Recent / Historic split

The D&L section is split into two subsections:

```
### Decisions & Learnings (Recent — last 14 days)
- 2026-06-10 — **topic** — ...
- 2026-06-09 — **topic** — ...

### Historic (older than 14 days · see git log for the build-up)
- 2026-05-XX — **topic** — ... [or one-line teasers pointing at archived files]
- 2026-Q1 — 14 entries archived → docs/decisions/2026-Q1.md
```

The Recent section is what Claude actively scans every turn. Historic stays minimal — one-liners with teasers. New entries always go into Recent.

## Pruning, graduation, archiving — four downward pressures

### 1. Strike-through on reversal
When a decision is reversed, strike-through with `~~...~~` and add a follow-up explaining the change. Don't silently delete.

### 2. Merge same-session clusters (the pre-14-days lever)
When a single work session lands 4+ entries about one piece of work — phased rollouts (`e2a-web`, `e2b-db`, `e3-consume`), same-feature aspects (`diff` + `diff-absolute`), bursts dated within ~48 hours of one another on the same area — **collapse them into one consolidated entry** with a single broader topic-tag. The compressed body keeps the load-bearing whys; the per-aspect detail moves to `docs/decisions/{date}-{topic}.md` if it's still wanted.

This is the *only* compaction action that works pre-14-days. Graduation requires 14-day stability (so a stable pattern hasn't proven itself yet); archive requires a date cutoff older than entries. When the audit fires "Compaction RECOMMENDED" but every entry is young, merge is what's left.

Triggers for merging:
- Multiple entries dated within ~48h on the same broad area (the topic-tags read as a numbered sequence, or as facets of one effort)
- The audit's mega-entry list is empty (no single entry is too big) but the *count* is over threshold
- Reviewing the cluster, the consolidated version reads at least as well as the spread

Merge does NOT graduate — the result is still in Decisions & Learnings, not Conventions. Reversibility: if a sub-decision later evolves independently, split it back out as a new entry that strikes through the consolidated one with a follow-up.

### 3. Graduation — when a pattern stabilizes
When the same `**topic-tag**` appears in 3+ entries AND the latest is ≥14 days old without a contradiction, the pattern is stable. **Graduate** it: rewrite as a one-line rule in **Conventions** (or **Gotchas** if it's a trap), strike through the D&L entries, leave a single graduation line `- YYYY-MM-DD — **topic** — graduated → see Conventions § X`.

The audit hook surfaces graduation candidates automatically. The skill's job is to act on the surfaced suggestion when the user OKs it.

### 4. Quarterly archive
Run `archive-decisions.py --cutoff YYYY-MM-DD --apply` at the end of each quarter. The script:
- Moves all entries older than the cutoff to `docs/decisions/{YYYY-Q}.md`
- Replaces them in CLAUDE.md with a single teaser line
- Preserves causality (strike-throughs, graduation links) in the archive

CLAUDE.md never grows monotonically — quarter ends, entries move out.

## Nested CLAUDE.md

A monorepo can carry `packages/api/CLAUDE.md` beside the root file, and Claude
Code loads it when work happens in that subtree. The audit walks up to three
levels deep (skipping `node_modules`, `target`, `build` and friends) and
size-checks whatever it finds.

Only the root file gets the full treatment — Decisions & Learnings parsing,
staleness, coverage — because that is where the log lives and reporting on five
files at every session start would be its own kind of noise.

## The hooks

### SessionStart audit (`audit-claude-md.py`)

Fires once per session. Reads CLAUDE.md, identifies:
- D&L section >300 lines OR >35 entries → "compaction RECOMMENDED"
- D&L >200 lines OR >25 entries → "consider compaction"
- Any entry >800 chars → split or compact candidate
- Any topic tag with 3+ entries → graduation candidate
- **Staleness** (predicates in `freshness.py`, the shared vendorable core) — entries citing backticked artifacts `git grep` can no longer find; version pins a build file (`pom.xml`, `package.json`, `Cargo.toml`, `go.mod`, `pyproject.toml`) now contradicts; and "latest is `V27`"-style sequence facts where the tree holds a higher-numbered file. All grounded in the tree, silent when parsing is uncertain → strike/update candidates
- **Coverage gaps** — the one check that pushes *up* (see below)
- **Capture-side states** (issue #37) — `unadopted` (a hand-rolled gotchas/learnings section with bullets but zero parseable D&L entries → offer the migration); `empty log` (20+ commits, docs/ markdown ≥5× CLAUDE.md, no D&L entries — the learning is going somewhere that doesn't load every turn); docs **recurrence** ("the third time…" self-counting language in docs/ — a rule begging to graduate); **layout drift** (a git-tracked top-level dir CLAUDE.md never mentions, and the reverse: a mentioned `dir/` gone from the tree — the plain layout check is one-shot and satisfied forever, this is what keeps prose tracking the tree; foreign paths are filtered by requiring the dir to have existed in this repo's git history). Both drift directions name the **edit**, not just the finding — add the line, or strike it — because a flag a reader must translate into an action is a flag that gets skimmed past

Silent when healthy. When triggered, emits `hookSpecificOutput.additionalContext` so the assistant sees the recommendation and can propose action.

### PreToolUse lint (`lint-claude-md.py`)

Fires before any `Write|Edit` of CLAUDE.md. Reads the proposed content, validates that any new D&L entries have:
- Valid `YYYY-MM-DD` date prefix
- A `**topic-tag**` (bold, kebab-case)
- Body ≤200 chars

If any entry violates, denies with a `reason` explaining which line + how to fix. The assistant retries with a corrected entry.

### Capture triggers (`capture-triggers.py`) — default OFF

The write path the other hooks never had. Two opt-in triggers
(`.claude/evolving-claude-md/config.json`), off until calibration measures
their noise (the retired gotchas check's 59%-fire lesson gates these too):

- **Session-end capture** (`"capture_prompt": "session-end"`, Stop hook) —
  commits + edits but CLAUDE.md untouched and no `docs/decisions/` file →
  block the stop once: nominate 0–3 entries. Zero is explicitly allowed.
- **Commit mining** (`"commit_mining": true`, PostToolUse on Bash) — a commit
  message with gotcha-shaped language ("turns out", "silently", "reports
  success") is a finished learning; suggest promoting it while context is hot.

Both prompts route: repo-durable, team-relevant → a D&L entry here;
machine-personal or private → the `learn-on-failure` skill to user memory.
One capture engine, two destinations — this plugin owns the triggers,
learn-on-failure owns the memory-side write path.

### Parallel lanes: spool, don't collide

N agents working one repo at once are N writers on one file, and the collision
is invisible until integration. Measured on one 2,400-commit repo running
worktree lanes: **86 of 257 non-merge `CLAUDE.md` edits were made on lane
branches, and all 50 merge commits touching the file were resolving them.**

So a lane never edits `CLAUDE.md`:

- **Lane** (a linked git worktree — the signal that siblings are running; or
  any non-default branch with `"lane_spool": "branch"`). The session-end prompt
  routes its nominations to `.claude/evolving-claude-md/incoming/<branch>.md`.
  One file per lane, so distinct paths merge cleanly and the conflict class
  disappears rather than being resolved. An ordinary feature branch is *not* a
  lane by default: one writer at a time merges fine, and diverting it would be
  a false positive.
- **Integrator**, once, on the default branch: `capture-triggers.py fold`
  prints every lane's nominations together and flags near-duplicates across
  lanes (five lanes on one epic learn the same lesson five times). Apply the
  bar, write the surviving entries into `CLAUDE.md` as one writer — so the
  lint hook still gates their format — then delete the folded files.

Folding is deliberately a human/main-session step, not another hook: only a
reader holding all the lanes at once can dedup them.

### PostCompact audit

Re-runs `audit-claude-md.py` after Claude Code compacts the conversation context. Same output shape as SessionStart. Keeps the assistant aware of CLAUDE.md state across a compaction without paying to re-read the whole file.

## Tuning the thresholds per repo

Every threshold and check in this skill is overridable per repo (and globally)
in `.claude/evolving-claude-md/config.json` — the full key list, defaults and
resolution order are in [references/setup-and-tuning.md](references/setup-and-tuning.md).

## Where an entry goes — CLAUDE.md vs `.claude.local.md`

`CLAUDE.md` is committed and shared; `.claude.local.md` is gitignored and yours.
Both load into context the same way, so the split is about *audience*, not size.

| Goes in `CLAUDE.md` | Goes in `.claude.local.md` |
|---|---|
| Decisions the team is bound by | How **your** machine happens to be set up |
| Conventions, gotchas, architecture | Absolute paths under your home directory |
| Anything true for every clone | Personal tokens, local ports, scratch dirs |
| Why a tradeoff was made | "the wrapper is broken on my box, I use `mvn`" |

The test is one question: **would this still be true on a teammate's laptop, in
CI, and in a fresh clone?** No means local.

Two things make this easy to get wrong. A machine-specific fact often *feels*
like a project fact when you're the only person working in the repo — and an
absolute path with your username in it is the most common way a personal detail
gets committed. `~/` is fine; `/home/alex/…` and `/Users/alex/…` are not.

When a learning is genuinely mixed — a real project decision plus a local
workaround — split it. The decision goes in the shared file with the reasoning,
the workaround goes local.

The audit size-checks `.claude.local.md` alongside the shared file, since it
costs the same context whichever file it sits in.

## Coverage — the one upward check

Every other check pushes content DOWN; this one asks whether the essentials are
there at all — a build file on disk with no matching command in CLAUDE.md, or a
many-directory repo with no layout prose. Grounded in the tree, never a generic
checklist. Full reasoning: [references/audit-checks.md](references/audit-checks.md).

## Structure review

The file's shape evolves with the project too: sections that outgrew their
heading, content in the wrong place, headings the tree no longer justifies.
Recommend, don't rewrite — and respect the measured hierarchy (presence ≫
brevity ≫ consistency ≫ structure) in
[references/claude-md-best-practices.md](references/claude-md-best-practices.md).
Procedure: [references/audit-checks.md](references/audit-checks.md).

## Quality bar for entries

Each entry passes all three:
- **Specific** — names the thing decided ("switched Mapbox → Leaflet"), not the area ("map work").
- **Sourced** — the *why* exists (constraint, incident, preference, tradeoff).
- **Actionable** — a future contributor can judge whether the entry still applies to a new edge case.

## Setup

Installed as a plugin the hooks come wired. Manual install, hook JSON and the
verification steps: [references/setup-and-tuning.md](references/setup-and-tuning.md).

## The quality gate

One more script ships beside the hooks: `test-harness.py`. It is not part
of the runtime and the hooks never call it — it is the release gate, run with
`make test-evolve` (or `python3 test-harness.py` from the skill directory)
after any change to the audit or lint scripts. Read it as documentation of the
checks' intended behaviour; run it before shipping a change to them. It covers
the coverage checks, the freshness detectors (fire and non-fire cases each),
the per-repo config resolution, companion-file discovery,
and the hook's exit-0/valid-JSON contract — with a pinned zero-false-positive
calibration across real repos.

## Common failure modes

- **The log accumulates without pruning.** The audit hook screams at you; act on it.
- **Mega-entries.** The lint hook blocks them at edit time. If you bypass and it lands anyway, the audit catches it.
- **Topic tag inconsistency.** Lint enforces presence; the audit surfaces clustering. Pick existing tags before inventing new ones.
- **Graduating too eagerly.** A pattern with 3 entries spread across one week isn't stable — wait 14 days minimum.
- **Skipping the archive.** Quarterly archive is operational; nothing automates it. Calendar reminder.
- **The log is never written to.** Every other failure mode assumes entries exist. If a session ends with commits but no new entry, the mechanism has failed *silently* — which is worse than failing loudly. A repo whose findings all live in `docs/` has this failure; the capture-side audit states and the (opt-in) capture triggers exist for exactly this.

## Boundary — this skill vs `memory-hygiene`

This skill governs `CLAUDE.md` and its companions: repo-scoped, committed,
human-authored with the agent proposing. The *other* half of the loaded
context — the agent-written memory under `~/.claude/projects/<slug>/memory/`
— belongs to the sibling `memory-hygiene` plugin. Different artifact,
different failure mode: bloat here makes instructions get ignored, rot there
makes the agent confidently recall something false. So this skill prunes
down; that one re-verifies and invalidates. They share one `freshness.py`
core (vendored in both) so "is this fact still true on disk?" has exactly
one implementation. "Make CLAUDE.md evolve" is this skill; "my memory has
gone stale" is that one.
