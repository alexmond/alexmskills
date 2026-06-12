---
name: system-design
description: Design a scalable system — architecture, data flow, APIs, schema, caching — then implement its minimal production version, applying the repo's evolving `system-design` role (.claude/roles/system-design.md). Invoke explicitly.
argument-hint: "[system / feature to design]"
disable-model-invocation: true
---

# System design + implementation

Target: $ARGUMENTS

1. **Load the role.** If `.claude/roles/system-design.md` exists, read it — it is the canonical, evolving copy. If not, read [role.md](role.md) (the seed shipped with this skill), copy it verbatim to `.claude/roles/system-design.md`, then proceed.
2. **Apply it.** Adopt the Charter and Body; honor every entry under `## Learnings (core)` and `## Learnings (solo)`.
3. **Work the target** following the Body's method and deliverables.
4. **Capture a learning.** If this run surfaced a durable, reusable lesson (a fix that took more than one cycle, a stack- or repo-specific gotcha, a stated user preference), append one line under `## Learnings (solo)` in `.claude/roles/system-design.md`: `- YYYY-MM-DD — <one sentence>`. Don't log routine one-pass outcomes.
