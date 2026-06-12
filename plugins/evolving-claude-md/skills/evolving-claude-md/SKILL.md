---
name: evolving-claude-md
description: Set up CLAUDE.md to maintain a living Decisions & Learnings log that the assistant updates as the project evolves. Use when initializing a CLAUDE.md, when the user asks for "learnings", "decisions log", "project memory in CLAUDE.md", "make CLAUDE.md evolve", or when a CLAUDE.md exists but has no mechanism for keeping itself current. Complements (does not replace) the built-in `init` skill — `init` bootstraps the description of the codebase; this adds the mechanism for the file to grow without bloating.
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

## When to invoke this skill

The assistant should invoke when the user says any of:
- "add learning mechanism to CLAUDE.md", "make CLAUDE.md evolve", "self-updating CLAUDE.md"
- "decisions log", "ADR-style notes in CLAUDE.md"
- "how do we keep CLAUDE.md current", "CLAUDE.md should grow with the project"
- "compact CLAUDE.md", "CLAUDE.md is getting too big"
- the user opens a CLAUDE.md that lacks any change-management structure and signals dissatisfaction

Don't invoke if the user only wants to document the codebase — use `init` for that.

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

## Pruning, graduation, archiving — three downward pressures

### 1. Strike-through on reversal
When a decision is reversed, strike-through with `~~...~~` and add a follow-up explaining the change. Don't silently delete.

### 2. Graduation — when a pattern stabilizes
When the same `**topic-tag**` appears in 3+ entries AND the latest is ≥14 days old without a contradiction, the pattern is stable. **Graduate** it: rewrite as a one-line rule in **Conventions** (or **Gotchas** if it's a trap), strike through the D&L entries, leave a single graduation line `- YYYY-MM-DD — **topic** — graduated → see Conventions § X`.

The audit hook surfaces graduation candidates automatically. The skill's job is to act on the surfaced suggestion when the user OKs it.

### 3. Quarterly archive
Run `archive-decisions.py --cutoff YYYY-MM-DD --apply` at the end of each quarter. The script:
- Moves all entries older than the cutoff to `docs/decisions/{YYYY-Q}.md`
- Replaces them in CLAUDE.md with a single teaser line
- Preserves causality (strike-throughs, graduation links) in the archive

CLAUDE.md never grows monotonically — quarter ends, entries move out.

## The three hooks

### SessionStart audit (`audit-claude-md.py`)

Fires once per session. Reads CLAUDE.md, identifies:
- D&L section >300 lines OR >35 entries → "compaction RECOMMENDED"
- D&L >200 lines OR >25 entries → "consider compaction"
- Any entry >800 chars → split or compact candidate
- Any topic tag with 3+ entries → graduation candidate

Silent when healthy. When triggered, emits `hookSpecificOutput.additionalContext` so the assistant sees the recommendation and can propose action.

### PreToolUse lint (`lint-claude-md.py`)

Fires before any `Write|Edit` of CLAUDE.md. Reads the proposed content, validates that any new D&L entries have:
- Valid `YYYY-MM-DD` date prefix
- A `**topic-tag**` (bold, kebab-case)
- Body ≤200 chars

If any entry violates, denies with a `reason` explaining which line + how to fix. The assistant retries with a corrected entry.

### PostCompact audit

Re-runs `audit-claude-md.py` after Claude Code compacts the conversation context. Same output shape as SessionStart. Keeps the assistant aware of CLAUDE.md state across a compaction without paying to re-read the whole file.

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
