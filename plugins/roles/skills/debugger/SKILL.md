---
name: debugger
description: Investigate a bug step by step, find the true root cause, and ship a robust production-ready fix, applying the repo's evolving `debugger` role (.claude/roles/debugger.md). Invoke explicitly.
argument-hint: "[error / failing behavior]"
disable-model-invocation: true
---

# Senior production debugging

Target: $ARGUMENTS

1. **Load the role.** If `.claude/roles/debugger.md` exists, read it — it is the canonical, evolving copy. If not, read [role.md](role.md) (the seed shipped with this skill), copy it verbatim to `.claude/roles/debugger.md`, then proceed.
2. **Apply it.** Adopt the Charter and Body; honor every entry under `## Learnings (core)` and `## Learnings (solo)`.
3. **Work the target** following the Body's method and deliverables.
4. **Capture a learning.** If this run surfaced a durable, reusable lesson (a fix that took more than one cycle, a stack- or repo-specific gotcha, a stated user preference), append one line under `## Learnings (solo)` in `.claude/roles/debugger.md`: `- YYYY-MM-DD — <one sentence>`. Don't log routine one-pass outcomes.
