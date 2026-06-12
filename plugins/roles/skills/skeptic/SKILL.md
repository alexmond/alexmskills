---
name: skeptic
description: Pressure-test a plan, finding, or design — steelman it, attack correctness/necessity/cost, and deliver a REFUTED / HOLDS / HOLDS-WITH-CUTS verdict — applying the repo's evolving `skeptic` role (.claude/roles/skeptic.md). Invoke explicitly.
argument-hint: "[plan / finding / design to pressure-test]"
disable-model-invocation: true
---

# Skeptic pressure-test

Target: $ARGUMENTS

1. **Load the role.** If `.claude/roles/skeptic.md` exists, read it — it is the canonical, evolving copy. If not, read [role.md](role.md) (the seed shipped with this skill), copy it verbatim to `.claude/roles/skeptic.md`, then proceed.
2. **Apply it.** Adopt the Charter and Body; honor every entry under `## Learnings (core)` and `## Learnings (solo)`.
3. **Work the target** following the Body's method and deliverables.
4. **Capture a learning.** If this run surfaced a durable, reusable lesson (a fix that took more than one cycle, a stack- or repo-specific gotcha, a stated user preference), append one line under `## Learnings (solo)` in `.claude/roles/skeptic.md`: `- YYYY-MM-DD — <one sentence>`. Don't log routine one-pass outcomes.
