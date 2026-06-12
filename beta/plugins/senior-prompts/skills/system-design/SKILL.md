---
name: system-design
description: Design a scalable system then implement its minimal production version, like a senior systems architect — architecture, components, data flow, APIs, schema, caching, then code.
argument-hint: "[system / feature to design]"
disable-model-invocation: true
---

# System design + implementation

Target: $ARGUMENTS

_First, skim `.claude/senior-prompts/learnings.md` (created on first run) for lessons already captured in this repo, and apply them._

Think like a senior systems architect. Design for scale, then build the **minimal production
version** — not a diagram-only exercise.

1. **Architecture** — high-level design and the major decisions (with trade-offs).
2. **Component structure** — services/modules and their responsibilities.
3. **Data flow** — how requests and data move through the system.
4. **API design** — the contracts between components.
5. **Database schema** — data model, relationships, indexes.
6. **Caching strategy** — what to cache, where, and how it's invalidated.
7. **Implementation code** — the minimal but real production version.

Call out the scaling limits and what you'd add at the next order of magnitude.

## Capture a learning
If this run surfaced a durable, reusable lesson — a fix that took more than one cycle, a stack- or repo-specific gotcha, or a preference the user stated — append one line to `.claude/senior-prompts/learnings.md`:

```
- YYYY-MM-DD — system-design — <the lesson, one sentence>
```

Don't log routine, one-pass outcomes. Keep it to a single line; the SessionStart hook recommends compaction when the log grows.
