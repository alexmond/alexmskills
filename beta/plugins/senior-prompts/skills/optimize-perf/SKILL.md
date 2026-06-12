---
name: optimize-perf
description: Optimize code like a performance engineer — find bottlenecks, inefficient logic, and unnecessary work, then improve speed, memory, and scalability with measured, behavior-preserving changes.
argument-hint: "[code / path / hot path]"
disable-model-invocation: true
---

# Performance optimization

Scope: $ARGUMENTS

_First, skim `.claude/senior-prompts/learnings.md` (created on first run) for lessons already captured in this repo, and apply them._

Think like a performance engineer. Optimize for **speed, memory usage, and scalability** — but
measure, don't guess.

1. **Performance issues** — bottlenecks, inefficient logic/algorithms, and unnecessary work (e.g.
   redundant rendering, N+1 queries, repeated allocations). Cite `file:line`.
2. **Optimization strategy** — ranked by impact vs. risk, with the expected win for each.
3. **Improved code** — apply the high-impact changes; keep behavior identical.

State how to verify each gain (benchmark, profile, or complexity argument). Don't micro-optimize
cold paths.

## Capture a learning
If this run surfaced a durable, reusable lesson — a fix that took more than one cycle, a stack- or repo-specific gotcha, or a preference the user stated — append one line to `.claude/senior-prompts/learnings.md`:

```
- YYYY-MM-DD — optimize-perf — <the lesson, one sentence>
```

Don't log routine, one-pass outcomes. Keep it to a single line; the SessionStart hook recommends compaction when the log grows.
