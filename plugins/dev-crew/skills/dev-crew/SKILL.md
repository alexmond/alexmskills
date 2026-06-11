---
name: dev-crew
description: >-
  Use this to take a coding task through a role-based delivery relay
  (architect -> dev -> qa -> deployer and beyond), where each role runs as a
  subagent on its own model tier. Trigger on "run the crew on", "ship this
  feature", "build and test X", "take this through the cycle", or any
  multi-step implementation/refactor/release task that benefits from separated
  design, build, verify, and deploy phases. The roster is editable per task and
  self-evolves: roles and their model tiers are added, promoted, demoted, and
  graduated into each repo's CLAUDE.md as the skill learns the codebase's cycle.
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Task
---

# dev-crew

A self-evolving software delivery crew. The main session acts as the
**conductor**: it selects which roles a task needs, delegates each phase to a
role **subagent** (which carries its own model and tool scope), passes work
between roles through shared handoff files, gates risky transitions, and writes
back what it learned so the crew gets better-tuned to this codebase over time.

This is the execution counterpart to `brainstorm-panel`. Panel converges on
*what* to build; crew runs the *building*. They compose — a panel outcome can be
handed straight to the crew as the task brief.

## Who orchestrates

The **orchestrator is the main Claude Code session** with this skill loaded —
not a subagent. The skill is instructions that make that session act as the
**conductor**: read context, name the category, propose and run the roster,
delegate each phase to a role subagent via the Task tool, receive their file
handoffs, enforce the gates, write the log and graduation.

Roles report **up** to the conductor and hand off to each other only through
files — they never call each other directly. The conductor's model and each
role's model are **independent**: a subagent runs on its own frontmatter model
and inherits nothing of the conductor's context or system prompt.

Run the conductor on **`opus`** (or `sonnet` to economize). Never run it on
`fable`: the conductor is the always-on seat that emits the most coordination
tokens, and at 2x-Opus rates that is the worst place to spend Fable. Fable lives
in specific role bodies on qualifying tasks (see Fable escalation policy), gated
behind an explicit go.

## Files this skill owns

- `roles.md` — the canonical role registry: role -> model -> tools -> status -> learnings. **Read this first, every run.**
- `log.md` — append-only run log; the substrate the learning loop reads from.
- `templates/role-template.md` — scaffold for minting a new role subagent.
- `templates/CLAUDE-md-block.md` — the `## Dev crew` block graduated into a repo.
- Per-run scratch lives in `<repo>/.claude/dev-crew/runs/<run-id>/` (handoff files, never committed unless the user asks).

Role **subagents** live in `~/.claude/agents/dc-*.md` (cross-repo defaults) and
may be overridden per repo in `<repo>/.claude/agents/dc-*.md` (project wins on
name collision). The registry in `roles.md` is the index over those files.

## Init: profile the project (once per repo)

Before the first run in a repo — and on demand via "re-profile" after a stack
change — the conductor delegates a read-only scan to **`dc-scout`** (haiku),
which writes `<repo>/.claude/dev-crew/PROFILE.md`. Delegating keeps the scan's
grep-heavy output out of the conductor's context and off an expensive model.

The profile detects languages and versions, build/package tool, frameworks, the
test stack, the static-analysis quality gate, CI system, deploy targets, domain,
and the conventions in `CLAUDE.md`. It then **drives the crew's tuning**:

- **Roster** — which roles each category gets by default, and which candidate
  roles to pre-arm (schema/migration files present -> stage migration-specialist;
  large convention-heavy codebase -> stage reviewer).
- **Role prompts** — qa is wired to the repo's *actual* quality-gate command;
  deployer is wired to the repo's *actual* CI/deploy target, not a generic one.
- **Model tier for `dev`** — lighter for mainstream, idiomatic stacks the model
  handles fluently; heavier for exotic, low-resource, or correctness-critical
  code. This is where "seniority" actually lives: it's a per-task tier dial set
  from the profile and category, not a separate junior/senior role.

If `PROFILE.md` already exists, intake reads it instead of re-scanning. The
profile and the graduated `## Dev crew` block are complementary: the profile is
the *facts* about the repo; the block is the *learned patterns* on top of them.

## Operating cycle

### 1. Intake
Read, in order: `PROFILE.md` (run `dc-scout` first if absent); the task brief;
the repo's `CLAUDE.md` (especially any `## Dev crew` block); this skill's
`roles.md`; recent `log.md` entries for this repo. Restate the task in one line
and name the task **category** (e.g. `feature`, `bugfix`, `refactor`,
`schema-change`, `perf`, `release`, `infra`). Profile + category drive roster
selection.

### 2. Roster selection — editable checkpoint
From `roles.md`, pick the minimal set of roles this category needs. Prefer the
lineup `PROFILE.md` recommends and the repo's `## Dev crew` block confirms for
this category. Set `dev`'s tier from the profile's recommendation for this repo
adjusted for this task's difficulty. Present an **editable roster** and STOP for
the user to adjust:

```
Roster for: <task, category>
  1. architect   (opus,   high)   — design + interface contract + ADR
  2. dev         (sonnet, high)   — implement against the contract
  3. qa          (sonnet, high)   — tests + review against done-criteria
  4. deployer    (haiku,  medium) — build/validate; STOPS before irreversible ops
Add / drop / reorder / re-tier any role, or say "go".
```

Never run the relay before the user confirms or edits the roster. The user may
add a role that does not exist yet — if so, follow **New-role protocol** before
running.

### 3. Run the relay
For each active role in order, delegate to its `dc-<role>` subagent via the Task
tool. Each role's `model` and tool scope come from its subagent frontmatter — do
**not** pass a global model override (see the `CLAUDE_CODE_SUBAGENT_MODEL`
warning below). Pass work between roles through files in the run directory:

- architect writes `PLAN.md` + `CONTRACT.md` (interfaces, done-criteria).
- dev reads those, implements, writes `CHANGES.md` (what changed + how to verify).
- qa reads `CONTRACT.md` + `CHANGES.md`, writes/runs tests, writes `QA.md` with a pass/fail verdict against each done-criterion.
- deployer reads `QA.md`; proceeds only on a pass.

After each role returns, the conductor summarizes the handoff in one short
paragraph and checks the gate before the next role. Whether it then **pauses for
you or continues** depends on the steering mode (see Steering). The default
pauses at each handoff so you can redirect.

### 4. Gates
- **QA gate:** the relay does not advance to deployer (or to "done") on a QA
  fail. On fail, route back to dev with `QA.md` as the defect list, max two
  loops before escalating to the user.
- **Deploy gate (hard):** deployer may run idempotent/dry checks freely
  (`build`, `lint`, `--dry-run`, `kubectl diff`, `docker build`), but must
  **stop and surface the exact irreversible commands** (apply, push, publish,
  release, prune, drop) for explicit user go-ahead before executing them. This
  holds even when the session runs with permissions skipped. See safety rails.

### 5. Log
Append a structured entry to `log.md` (schema in that file): run-id, repo,
category, final roster with models, per-role outcome, gate events, defects
caught and where, model-fit notes, and anything that smells like a missing role.

## Steering: you stay in the driver's seat

The crew runs *your* cycle; it does not take it from you. You can redirect at any
phase boundary, and the handoff files are the editable source of truth — your
idea becomes an edit to `CONTRACT.md`/`PLAN.md` that every downstream role reads.

**Steering mode** (set at the roster checkpoint, change anytime):
- `autopilot` — run the relay through, pausing only at hard gates (QA fail, deploy).
- `checkpoint` (default) — pause after each role's handoff; show the summary; you say "continue" or steer.
- `co-drive` — propose each role's plan *before* running it; you approve or adjust first.

**Injecting an idea mid-run.** Say it at any pause. The conductor classifies and routes:
- refines the approach -> amend `PLAN.md`/`CONTRACT.md`, re-run only the affected phase
- changes scope -> re-scope the contract; note what's now out of scope
- "use X here" -> hand it to the active role as a constraint
- swap a role or re-tier a model -> edit the roster mid-run
- "go back" -> re-open a prior phase with your input as added context
- "I'll handle this part" -> mark a phase done and hand in its artifact yourself

No teardown, no restart — the relay resumes from the affected phase.

**Granularity.** Interrupt points are phase boundaries, not mid-role: a subagent
runs to completion within one invocation. For finer control, scope phases
smaller (one work-item per `dev` pass) — which also pairs with the `tech-lead`
fan-out.

**Your steering is signal.** Every injected decision is logged (`steering:` in
the run entry). Repeated injections of the same kind graduate into the repo's
conventions, a role's prompt, or a new role. Adjusting the cycle is how the crew
learns your cycle — it's a feature of the loop, not a fight with it.

## Self-learning loop

The crew tunes itself by reading `log.md` and writing back. Run the graduation
pass automatically at the end of a run, or on demand ("graduate the crew").

**Graduate a lineup.** When the same category has run a stable roster ≥3 times
with good outcomes, write/update that category's recommended lineup in the
repo's `## Dev crew` block (use `templates/CLAUDE-md-block.md`). That block is
what intake reads next time, so the roster checkpoint pre-fills correctly.

**Re-tier a model.** Mine `log.md` for model-fit signals and propose changes,
each with its rationale logged:
- *Promote* when a role on a lighter tier repeatedly misses (e.g. qa on `haiku`
  let edge-case bugs through twice -> propose `sonnet`).
- *Demote* when a role's output never needed the heavier tier (e.g. deployer on
  `sonnet` only ever ran mechanical steps -> propose `haiku`).
- *Escalate* an architect to `fable` for designs that span more than a single
  sitting or touch many subsystems.
Apply re-tiers by editing the role's subagent `model` frontmatter and the
registry row; record old->new + reason in `roles.md` and `log.md`.

**Graduate a steer.** When the `steering:` log shows you injecting the same kind
of correction ≥3 times (a library/pattern preference, a recurring re-scope, a
convention the crew keeps missing), promote it: into the repo's `CLAUDE.md`
conventions, into the relevant role's prompt, or — if it's really a missing
owner — into a new role. Your repeated adjustments are the highest-signal
training data the loop has.

**Mint a new role.** When `log.md` shows a recurring failure class that no
current role owns (e.g. repeated migration breakage, perf regressions slipping
past qa, security findings late), follow the **New-role protocol**:
1. Name the role and its single job + done-criteria.
2. Scaffold `~/.claude/agents/dc-<role>.md` from `templates/role-template.md`,
   set its `model`/`tools`/`effort`, read-only tools for review roles.
3. Register it in `roles.md` with status `probationary`.
4. Use it in the relevant category; after ≥3 clean runs, flip to `stable` and it
   becomes eligible for graduation into repo `## Dev crew` blocks.
Retire or merge roles that go unused or overlap.

**Scope of graduation.** Repo-specific patterns -> that repo's `## Dev crew`
block. Patterns that hold across repos (a model re-tier that's right everywhere,
a broadly useful new role) -> the user-level `roles.md` defaults, so every repo
inherits them.

## Fable escalation policy

Fable is the top tier and is treated as a **deliberate, gated escalation — never
a default**. It is not its own role; it is a tier that two roles can be bumped
to when the work genuinely justifies it.

**Eligible only when** the task is long-horizon and would otherwise be broken
into pieces, spans multiple subsystems, or is an ambiguous root-cause /
investigation problem — the cases where Fable's investigate-before-acting and
self-verification actually pay for the cost. Eligible roles: `architect` (large
cross-subsystem designs) and `lead` (deep root-cause / multi-system
investigation). Never `dev`, `qa`, or `deployer` — their work is mechanical and
Fable there is pure waste.

**Gate (hard).** The conductor never silently selects Fable. When a role
qualifies, the conductor proposes the bump **in the roster checkpoint with an
explicit cost line**, and runs it only on the user's go:

```
  1. architect  (FABLE, high)  — cross-subsystem redesign; spans >1 sitting
       ⚠ Fable ≈ 2x Opus quota burn. After 2026-06-22 it draws usage credits
         at API rates ($10/$50 per Mtok). Confirm, or keep architect on opus.
```

Default the same role to `opus` in the proposal so declining is the easy path.

**Auto-fallback caveat.** Fable runs safety classifiers for cybersecurity and
biology. A flagged request silently reroutes to Opus, and the classifier can
trip on the *first* request from a repo's `CLAUDE.md` or git status alone — so a
"Fable architect" on a security-adjacent repo may quietly be an Opus architect.
If a run was supposed to use Fable, confirm in the transcript that it actually
did before crediting any outcome to it in `log.md`.

**Availability.** Fable requires Claude Code v2.1.170+ and is not selectable
under zero-data-retention. If unavailable, fall back to `opus` and note it.

**Learning-loop rule.** Because Fable is expensive, the graduation loop must
**never** promote a Fable bump into a repo's default lineup. Fable stays a
per-run, opt-in escalation. The loop may *suggest* "this category tends to need
the architect at Fable" as a note, but the gate fires every time regardless.

## Safety rails

- **Deploy gate is non-negotiable.** Irreversible operations always stop for an
  explicit go, regardless of session permission mode. The deployer subagent
  carries `permissionMode: default` and a prompt-level hard stop as belt and
  suspenders. If you run Claude Code with permissions skipped, this gate is the
  thing standing between an autonomous relay and an unreviewed prod/​homelab
  change — leave it in place.
- **Tool scope per role.** Review roles (qa, security-reviewer) get read-only
  tool allowlists so a verification step can't quietly rewrite the thing it's
  meant to check.
- **`CLAUDE_CODE_SUBAGENT_MODEL` overrides everything.** If that env var is set,
  every role collapses onto one model and per-role tiering is silently lost. The
  crew's whole point is per-role models — keep that var unset (or `inherit`)
  while using this skill.

## Install
See `INSTALL.md` in the bundle. In short: `skills/dev-crew/` -> `~/.claude/skills/`,
`agents/dc-*.md` -> `~/.claude/agents/`. Roles are then available in every repo;
each repo grows its own `## Dev crew` block as the crew learns it.
