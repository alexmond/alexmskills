---
name: clean-arch
description: Refactor code into clean architecture like a senior engineer — separate concerns, raise modularity, reduce coupling; structure improves while behavior stays the same.
argument-hint: "[module / path to restructure]"
disable-model-invocation: true
---

# Clean architecture rebuild

Scope: $ARGUMENTS

_First, skim `.claude/senior-prompts/learnings.md` (created on first run) for lessons already captured in this repo, and apply them._

Think like a senior engineer converting code to clean architecture. Separate concerns, increase
modularity, reduce coupling — **behavior unchanged, structure improved**.

1. **New folder/module structure** — the target layout and the layer boundaries.
2. **Architecture description** — responsibilities per layer and the dependency direction
   (dependencies point inward).
3. **Refactored code** — move logic into the new structure; keep public behavior identical.

Don't over-engineer: apply only the separation the code's actual complexity justifies.

## Capture a learning
If this run surfaced a durable, reusable lesson — a fix that took more than one cycle, a stack- or repo-specific gotcha, or a preference the user stated — append one line to `.claude/senior-prompts/learnings.md`:

```
- YYYY-MM-DD — clean-arch — <the lesson, one sentence>
```

Don't log routine, one-pass outcomes. Keep it to a single line; the SessionStart hook recommends compaction when the log grows.
