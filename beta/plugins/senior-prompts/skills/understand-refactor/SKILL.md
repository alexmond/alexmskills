---
name: understand-refactor
description: Understand an unfamiliar or large codebase and refactor it safely like a senior engineer who just joined — map architecture and data flow, then raise quality without changing behavior.
argument-hint: "[path or area to study]"
disable-model-invocation: true
---

# Understand & refactor a codebase

Scope: $ARGUMENTS

_First, skim `.claude/senior-prompts/learnings.md` (created on first run) for lessons already captured in this repo, and apply them._

Think like a senior engineer who just joined a large, unfamiliar codebase. First **understand**,
then improve — functionality stays identical, quality goes up.

1. **Architecture summary** — how it's structured, the main modules, and how data flows through them.
2. **Problem areas** — structural problems, duplicated code, performance bottlenecks, maintainability
   risks. Cite `file:line`.
3. **Refactoring strategy** — ordered, low-risk steps; what to change and why; what to leave alone.
4. **Improved code** — apply the safe refactors. Preserve behavior; lean on existing tests, or add
   characterization tests first where coverage is thin.

Rule: **behavior unchanged, quality enhanced.** No speculative rewrites — justify every change.

## Capture a learning
If this run surfaced a durable, reusable lesson — a fix that took more than one cycle, a stack- or repo-specific gotcha, or a preference the user stated — append one line to `.claude/senior-prompts/learnings.md`:

```
- YYYY-MM-DD — understand-refactor — <the lesson, one sentence>
```

Don't log routine, one-pass outcomes. Keep it to a single line; the SessionStart hook recommends compaction when the log grows.
