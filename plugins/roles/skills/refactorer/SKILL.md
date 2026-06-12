---
name: refactorer
description: Restructure code into clean architecture — separate concerns, raise modularity, reduce coupling, behavior unchanged — applying the repo's evolving `refactorer` role (.claude/roles/refactorer.md). Invoke explicitly.
argument-hint: "[module / path to restructure]"
disable-model-invocation: true
---

# Clean architecture rebuild

Target: $ARGUMENTS

1. **Load the role.** If `.claude/roles/refactorer.md` exists, read it — it is the canonical, evolving copy. If not, read [role.md](role.md) (the seed shipped with this skill), copy it verbatim to `.claude/roles/refactorer.md`, then proceed.
2. **Apply it.** Adopt the Charter and Body; honor every entry under `## Learnings (core)` and `## Learnings (solo)`.
3. **Work the target** following the Body's method and deliverables.
4. **Capture a learning.** If this run surfaced a durable, reusable lesson (a fix that took more than one cycle, a stack- or repo-specific gotcha, a stated user preference), append one line under `## Learnings (solo)` in `.claude/roles/refactorer.md`: `- YYYY-MM-DD — <one sentence>`. Don't log routine one-pass outcomes.
