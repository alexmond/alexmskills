---
name: builder
description: Scaffold a complete, production-ready application from scratch — architecture first, then a minimal but scalable MVP — applying the repo's evolving `builder` role (.claude/roles/builder.md). Invoke explicitly.
argument-hint: "[what to build]"
disable-model-invocation: true
---

# Build a complete application from scratch

Target: $ARGUMENTS

1. **Load the role.** If `.claude/roles/builder.md` exists, read it — it is the canonical, evolving copy. If not, read [role.md](role.md) (the seed shipped with this skill), copy it verbatim to `.claude/roles/builder.md`, then proceed.
2. **Apply it.** Adopt the Charter and Body; honor every entry under `## Learnings (core)` and `## Learnings (solo)`.
3. **Work the target** following the Body's method and deliverables.
4. **Capture a learning.** If this run surfaced a durable, reusable lesson (a fix that took more than one cycle, a stack- or repo-specific gotcha, a stated user preference), append one line under `## Learnings (solo)` in `.claude/roles/builder.md`: `- YYYY-MM-DD — <one sentence>`. Don't log routine one-pass outcomes.
