---
name: as
description: Run any registered role from the repo's evolving role repository (.claude/roles/) against a target — the generic solo dispatcher for roles that have no dedicated wrapper skill. Invoke explicitly.
argument-hint: "[role] [target]"
disable-model-invocation: true
---

# Run a role solo

Input: $ARGUMENTS — the **first word** is the role name; the rest is the target.

1. **Resolve the role.** Prefer the repo's instantiated copy `.claude/roles/<role>.md` (the
   canonical, evolving one; `registry.md` indexes these). If it's absent, check this plugin's
   bundled seeds alongside this skill at `../<role>/role.md` — if found, copy it verbatim to
   `.claude/roles/<role>.md` and use that. If the role exists in neither, list the available roles
   (repo `.claude/roles/*.md` plus the bundled `../*/role.md`, excluding `crew.md`/`panel.md`/
   `registry.md`/this `as` skill) and stop — don't improvise a persona.
2. **Apply it.** Adopt the role's Charter and Body; honor every entry under `## Learnings (core)`
   and `## Learnings (solo)`. Note `crew.md` and `panel.md` are consumer registries, not roles —
   never load them as personas.
3. **Work the target** following the Body's method and deliverables.
4. **Capture a learning.** If the run surfaced a durable, reusable lesson (a fix that took more
   than one cycle, a stack- or repo-specific gotcha, a stated user preference), append one line
   under `## Learnings (solo)` in the role file: `- YYYY-MM-DD — <one sentence>`. Don't log
   routine one-pass outcomes.

Charter and Body edits are **never** made during a run — propose them to the user instead
(identity changes are deliberate, user-gated).
