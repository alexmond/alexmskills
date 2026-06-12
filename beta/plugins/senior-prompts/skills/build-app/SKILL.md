---
name: build-app
description: Scaffold a complete, production-ready application from scratch like a senior full-stack engineer — architecture first, then a minimal but scalable MVP. Invoke explicitly to start a greenfield build.
argument-hint: "[what to build]"
disable-model-invocation: true
---

# Build a complete application from scratch

Target: $ARGUMENTS

_First, skim `.claude/senior-prompts/learnings.md` (created on first run) for lessons already captured in this repo, and apply them._

Think like a senior full-stack engineer shipping a real startup MVP. Design the system
**architecture first**, then build a **minimal but scalable** version — no throwaway scaffolding,
no toy code.

Work in this order and present each:

1. **Architecture** — components, boundaries, and the key technical decisions (with the *why*).
2. **File / folder structure** — the actual tree you'll create.
3. **Database schema** — tables/collections, relationships, indexes.
4. **API endpoints** — routes, methods, request/response shapes.
5. **UI architecture** — screens, component hierarchy, state/data flow.
6. **Complete code** — implement the MVP end to end; runnable, not pseudocode.

Constraints: pick a mainstream, well-supported stack unless told otherwise; keep the first version
minimal but structured so it scales; call out trade-offs and anything deliberately deferred.

## Capture a learning
If this run surfaced a durable, reusable lesson — a fix that took more than one cycle, a stack- or repo-specific gotcha, or a preference the user stated — append one line to `.claude/senior-prompts/learnings.md`:

```
- YYYY-MM-DD — build-app — <the lesson, one sentence>
```

Don't log routine, one-pass outcomes. Keep it to a single line; the SessionStart hook recommends compaction when the log grows.
