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

## What to log — six triggers

Append to **Decisions & Learnings** below whenever any of these happens — don't wait to be asked:

1. A non-trivial architectural decision (stack, schema, tradeoff resolved).
2. Durable user feedback (preferences, things to never do, validated approaches).
3. A non-obvious gotcha (build quirks, library traps, third-party API limits).
4. A convention established or revised.
5. A scope shift (something moved in/out, priorities reordered).
6. An external dependency or service added / replaced / removed.

## What NOT to log

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

## The three hooks

### SessionStart audit (`audit-claude-md.py`)

Fires once per session. Reads CLAUDE.md, identifies:
- D&L section >300 lines OR >35 entries → "compaction RECOMMENDED"
- D&L >200 lines OR >25 entries → "consider compaction"
- Any entry >800 chars → split or compact candidate
- Any topic tag with 3+ entries → graduation candidate
- **Coverage gaps** — the one check that pushes *up* (see below)

Silent when healthy. When triggered, emits `hookSpecificOutput.additionalContext` so the assistant sees the recommendation and can propose action.

### PreToolUse lint (`lint-claude-md.py`)

Fires before any `Write|Edit` of CLAUDE.md. Reads the proposed content, validates that any new D&L entries have:
- Valid `YYYY-MM-DD` date prefix
- A `**topic-tag**` (bold, kebab-case)
- Body ≤200 chars

If any entry violates, denies with a `reason` explaining which line + how to fix. The assistant retries with a corrected entry.

### PostCompact audit

Re-runs `audit-claude-md.py` after Claude Code compacts the conversation context. Same output shape as SessionStart. Keeps the assistant aware of CLAUDE.md state across a compaction without paying to re-read the whole file.

## Tuning the thresholds per repo

"Concise" is not a universal number. 40 KB is bloat in a library and reasonable
in a monorepo that genuinely has that much load-bearing context — so the shipped
defaults are a starting point, not a verdict, and every one is overridable.

Resolution order, later wins:

```
built-in defaults
  → ~/.claude/evolving-claude-md/config.json          (all your repos)
    → <repo>/.claude/evolving-claude-md/config.json   (this repo)
```

```json
{
  "file_warn_kb": 25,        "file_recommend_kb": 40,
  "lines_warn": 200,         "lines_recommend": 300,
  "entries_warn": 25,        "entries_recommend": 35,
  "mega_entry_chars": 800,   "topic_cluster": 3,
  "layout_min_dirs": 5,
  "coverage": true,          "nested": true
}
```

Name only the keys you want changed; the rest keep their defaults. Unknown keys
are ignored, and a corrupt config falls back to defaults rather than failing —
this runs on SessionStart, and a bad config file must never be the reason a
session starts badly.

Set `coverage: false` to drop the upward check, `nested: false` to stop looking
at companion files.

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

Every other check pushes content *down*: bloat, staleness, clustering, archiving. A
file can pass all of them and still be useless — well under every threshold,
perfectly formatted, and never saying how to run the tests. Coverage is the check
that asks whether the essentials are there at all.

Two gaps, both **grounded in the tree rather than in a checklist**:

| Gap | Fires only when |
|---|---|
| *no build/test command* | a build file exists (`pom.xml`, `package.json`, `Cargo.toml`, `go.mod`, `Makefile`, … — 12 supported) **and** CLAUDE.md never mentions its command |
| *nothing on layout* | the repo has 5+ meaningful top-level directories (generated ones like `target/`, `node_modules/` don't count) **and** CLAUDE.md never describes where anything lives |

Grounding is the whole design. A docs repo has no build command, and a
three-directory repo needs no layout section — a generic checklist nags both. On a
29-repo sample these two fired **zero** times, because every one of those repos
already covers what its tree justifies.

To decline a gap permanently, put the decision in the file itself:

```markdown
<!-- audit-skip: commands, layout -->
```

**Deliberately not checked: a "gotchas" section.** Measured on the same 29 repos it
fired on 17 (59%) — noise, not signal. Worse, those 17 were exactly the repos with
no D&L log, so it was only re-detecting "hasn't adopted this skill", which the audit
already says. Gotchas arrive by *graduation* from the log; the topic-cluster check is
the grounded way to prompt for them. Don't re-add it without data.

## Quality bar for entries

Each entry passes all three:
- **Specific** — names the thing decided ("switched Mapbox → Leaflet"), not the area ("map work").
- **Sourced** — the *why* exists (constraint, incident, preference, tradeoff).
- **Actionable** — a future contributor can judge whether the entry still applies to a new edge case.

## Setup checklist (manual install)

For a fresh project, when not installing via the marketplace plugin:

1. Append the **How this file evolves** section to CLAUDE.md (a compact version of the rules above).
2. Seed the Decisions & Learnings split: `### Decisions & Learnings (Recent — last 14 days)` + an empty `### Historic` section.
3. Copy the three scripts into `.claude/skills/evolving-claude-md/`:
   - `audit-claude-md.py`
   - `lint-claude-md.py`
   - `archive-decisions.py`
4. Add `.claude/settings.json` hooks pointing at them (SessionStart, PreToolUse, PostCompact) — see the plugin's `hooks/hooks.json` for the exact shape; replace `${CLAUDE_PLUGIN_ROOT}/skills/evolving-claude-md` with `.claude/skills/evolving-claude-md`.
5. Add the first real entry — usually the project goal.

The hooks need a single restart of the Claude Code session to register (settings reload). Installing as a plugin skips steps 3–4 entirely.

## Common failure modes

- **The log accumulates without pruning.** The audit hook screams at you; act on it.
- **Mega-entries.** The lint hook blocks them at edit time. If you bypass and it lands anyway, the audit catches it.
- **Topic tag inconsistency.** Lint enforces presence; the audit surfaces clustering. Pick existing tags before inventing new ones.
- **Graduating too eagerly.** A pattern with 3 entries spread across one week isn't stable — wait 14 days minimum.
- **Skipping the archive.** Quarterly archive is operational; nothing automates it. Calendar reminder.
