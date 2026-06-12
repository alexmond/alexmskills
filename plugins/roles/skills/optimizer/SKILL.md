---
name: optimizer
description: Find bottlenecks and unnecessary work, then improve speed, memory, and scalability with measured, behavior-preserving changes, applying the repo's evolving `optimizer` role (.claude/roles/optimizer.md). Invoke explicitly.
argument-hint: "[code / path / hot path]"
disable-model-invocation: true
---

# Performance optimization

Target: $ARGUMENTS

1. **Load the role.** If `.claude/roles/optimizer.md` exists, read it — it is the canonical, evolving copy. If not, read [role.md](role.md) (the seed shipped with this skill), copy it verbatim to `.claude/roles/optimizer.md`, then proceed.
2. **Apply it.** Adopt the Charter and Body; honor every entry under `## Learnings (core)` and `## Learnings (solo)`.
3. **Work the target** following the Body's method and deliverables.
4. **Capture a learning.** If this run surfaced a durable, reusable lesson (a fix that took more than one cycle, a stack- or repo-specific gotcha, a stated user preference), append one line under `## Learnings (solo)` in `.claude/roles/optimizer.md`: `- YYYY-MM-DD — <one sentence>`. Don't log routine one-pass outcomes.
