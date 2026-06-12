---
name: debug-root-cause
description: Investigate a bug like a senior debugging engineer in production — analyze step by step, find the true root cause, and propose a robust, production-ready fix rather than a band-aid.
argument-hint: "[error / failing behavior]"
disable-model-invocation: true
---

# Senior production debugging

Bug: $ARGUMENTS

_First, skim `.claude/senior-prompts/learnings.md` (created on first run) for lessons already captured in this repo, and apply them._

Think like a senior debugging engineer investigating a production incident. Analyze carefully and
reason step by step — do not guess-and-patch.

1. **What the code does** — the relevant behavior and the path involved.
2. **The problem** — precisely what's going wrong.
3. **Why it fails** — the true root cause, traced step by step (not the symptom).
4. **Edge cases** — related inputs or states that would also break.
5. **Fixed code** — a robust, production-ready fix that addresses the root cause, with a note on how
   to verify it.

If the root cause is uncertain, say what evidence would confirm it **before** changing code.

## Capture a learning
If this run surfaced a durable, reusable lesson — a fix that took more than one cycle, a stack- or repo-specific gotcha, or a preference the user stated — append one line to `.claude/senior-prompts/learnings.md`:

```
- YYYY-MM-DD — debug-root-cause — <the lesson, one sentence>
```

Don't log routine, one-pass outcomes. Keep it to a single line; the SessionStart hook recommends compaction when the log grows.
