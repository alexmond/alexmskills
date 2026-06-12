---
name: understand-refactor
description: Map an unfamiliar or large codebase and refactor it safely — behavior unchanged, quality raised — applying the repo's evolving `understand-refactor` role (.claude/roles/understand-refactor.md). Invoke explicitly.
argument-hint: "[path or area to study]"
disable-model-invocation: true
---

# Understand & refactor a codebase

Target: $ARGUMENTS

1. **Load the role.** If `.claude/roles/understand-refactor.md` exists, read it — it is the canonical, evolving copy. If not, read [role.md](role.md) (the seed shipped with this skill), copy it verbatim to `.claude/roles/understand-refactor.md`, then proceed.
2. **Apply it.** Adopt the Charter and Body; honor every entry under `## Learnings (core)` and `## Learnings (solo)`.
3. **Work the target** following the Body's method and deliverables.
4. **Capture a learning.** If this run surfaced a durable, reusable lesson (a fix that took more than one cycle, a stack- or repo-specific gotcha, a stated user preference), append one line under `## Learnings (solo)` in `.claude/roles/understand-refactor.md`: `- YYYY-MM-DD — <one sentence>`. Don't log routine one-pass outcomes.
