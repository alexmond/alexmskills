# dev-crew role registry

The canonical roster. The conductor reads this every run to know which roles
exist, what model each runs on, and what's been learned about them. Each row
maps to a subagent file at `~/.claude/agents/dc-<role>.md` (or a repo override
at `<repo>/.claude/agents/dc-<role>.md`).

## Row schema

```
### <role>
- subagent: dc-<role>
- model: <opus | sonnet | haiku | fable | full-id>   effort: <low|medium|high|xhigh|max>
- tools: <allowlist, or "read-only" / "inherit">
- status: <stable | probationary | retired>
- owns: <the single failure class / job this role is responsible for>
- done: <how we know this role's phase succeeded>
- learnings: <bullet history of re-tiers, defects caught/missed, tuning>
```

## Seed roster

### scout
- subagent: dc-scout
- model: haiku   effort: medium
- tools: read-only (Read, Grep, Glob, Bash)
- status: stable
- owns: the init project profile — stack, gate command, CI/deploy target, conventions
- done: PROFILE.md written with a concrete recommendations block
- learnings:
  - (seed) runs once per repo and on "re-profile"; never runs builds/tests (read-only scan)

### architect
- subagent: dc-architect
- model: opus   effort: high   (Fable-eligible: gated opt-in for cross-subsystem / multi-sitting designs — see SKILL.md Fable escalation policy; never auto-selected)
- tools: read-only + Write (plan files only)
- status: stable
- owns: design soundness — interfaces, data model, trade-offs, ADR
- done: PLAN.md + CONTRACT.md exist; interfaces and done-criteria are explicit and testable
- learnings:
  - (seed) start every contract with the verifiable done-criteria; dev and qa both key off them

### dev
- subagent: dc-dev
- model: sonnet   effort: high
- tools: Read, Write, Edit, Bash, Grep, Glob
- status: stable
- owns: implementation that satisfies CONTRACT.md without scope creep
- done: CHANGES.md written; code builds; self-verification steps pass
- learnings:
  - (seed) implement only what the contract specifies; flag, don't absorb, scope it didn't authorize

### qa
- subagent: dc-qa
- model: sonnet   effort: high
- tools: read-only + Bash (run tests only)
- status: stable
- owns: catching defects and contract violations before deploy
- done: QA.md gives a pass/fail verdict per done-criterion with evidence
- learnings:
  - (seed) verdict is per-criterion, not a blanket "looks good"; a single fail blocks the deploy gate

### deployer
- subagent: dc-deployer
- model: haiku   effort: medium
- tools: Read, Bash, Grep, Glob   (no Edit/Write to source)
- status: stable
- owns: getting validated changes out safely
- done: dry checks pass; the exact irreversible commands are staged and surfaced for go-ahead
- learnings:
  - (seed) never execute apply/push/publish/release/prune/drop without an explicit go, even under skipped permissions

## Candidate roles (mint when log.md shows the gap)

These are pre-described so the New-role protocol is one step when the need shows
up. None are installed until a recurring failure class justifies them.

- **lead** — opus, **Fable-eligible (gated)**, read-only + Write(plan). Owns: deep root-cause / multi-system investigation on ambiguous or circling failures. This is the natural Fable home alongside architect. **File `dc-lead.md` is already provided** (status: probationary) — register it `stable` after ≥3 clean runs. Use it when bugfix/debug loops repeatedly exceed two passes or a failure spans subsystems.
- **tech-lead** — opus/sonnet. Owns: decomposing a large contract into independent work items, dispatching parallel `dev` subagents (each tiered to its item), and integration review. Mint when single-threaded `dev` is the throughput bottleneck on big features. This is the real "senior" pattern — orchestration, not a model tier.
- **reviewer** — sonnet/opus, read-only. Owns: *craft* review — design fit, maintainability, idiomatic use of the stack — distinct from qa's correctness-against-criteria. Mint when the profile flags a large or convention-heavy codebase where craft drift is a risk.
- **security-reviewer** — opus, read-only. Owns: auth flows, input handling, secret exposure. Mint when security findings land late.
- **migration-specialist** — opus/sonnet. Owns: schema/data migrations + rollback. Mint when migrations break (or pre-armed by the profile when migration files exist).
- **perf-profiler** — sonnet. Owns: regressions in latency/throughput/memory. Mint when perf slips past qa.
- **docs-writer** — haiku. Owns: README/API/CHANGELOG drift. Mint when docs lag shipped behavior.
- **debugger** — sonnet/opus. Owns: reproduce-isolate-fix on stubborn failures. Mint when bugfix loops exceed two passes (escalates into `lead` if it spans subsystems).

## Seniority — a design note

There is intentionally **no junior/senior `dev`**. Seniority unbundles into axes
the crew already has:
- *Capability* is the **model tier** — "senior dev" is just `dev` on `opus`.
- *Cost arbitrage* is the **profile-driven per-task tier** — routine work runs
  `dev` cheap, hard work runs it heavy.
- *Parallel delegation* is the **tech-lead** candidate (fan-out + integration review).
- *Craft hierarchy* is the **reviewer** candidate (distinct from qa).

So seniority is a dial and two optional roles, not a set of titles. Adding
`junior-dev`/`senior-dev` would just rename the model tier and fragment the
roster. Mint tech-lead/reviewer when the work calls for them.

## Fable tier — usage note

Fable is an escalation **tier**, not a role. Only `architect` and `lead` may be
bumped to it, only via the roster-checkpoint gate, only for long-horizon /
cross-subsystem / ambiguous-investigation work. It burns ~2x Opus quota and,
after 2026-06-22, draws usage credits at API rates. The graduation loop never
promotes a Fable bump into a default lineup. Full rules: SKILL.md → Fable
escalation policy.

## Protocols (mirror SKILL.md)

**Add a role:** scaffold `~/.claude/agents/dc-<role>.md` from
`templates/role-template.md`, set model/tools/effort, add a row here with
`status: probationary`. Flip to `stable` after ≥3 clean runs.

**Re-tier a model:** edit the role's subagent `model` frontmatter and its row
here; append old->new + reason to that row's `learnings` and to `log.md`.

**Graduate a lineup:** when a category's roster is stable ≥3 runs, write it into
the repo's `## Dev crew` block via `templates/CLAUDE-md-block.md`.
