# Changelog

All notable changes to the **alexmskills** marketplace and its plugins.

Plugins are versioned **independently** — the authoritative version is each plugin's `plugin.json`.
This log groups changes by date and tags each entry with the plugin and the version it shipped in.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/); the marketplace itself is
unreleased/rolling (no global version).

## 2026-06-21

### Added
- **research-sweep 1.1.3** — closes the cross-run learning gap (the only orchestrator without
  a per-run log). Four changes:
  - **Per-run log** at `.claude/research-sweep/log.md` (seeded from a shipped schema), with
    fields for run-id, roster, partition, per-role volume + thin-diagnosis, verifier findings
    (sample, fabrications, duplicates, gaps, verdict), dedup hotspots, source-trust, steering,
    outcome, and graduations.
  - **Thin-agent diagnosis** — classifies thin results as *slice-thin* (corpus sparse → merge /
    lower target) vs *agent-thin* (web denied / weak prompt / wrong angle → re-run / re-role),
    mirroring crew's capability-vs-ownership ladder. Logged as `thin:` events.
  - **Demote / retire rule** — two thin runs (no fix) → probationary; three → retired. Three
    user-cut events at the roster gate also retire the role.
  - **Graduation block** — patterns holding across ≥3 sweeps in a repo graduate into a
    `## Research sweep` block in CLAUDE.md (default roster, authoritative sources, untrusted
    sources, ID-disambiguation rules, skip-angles); graduated entries are pruned from the log.

## 2026-06-14

### Added
- **tune-repo 0.1.1** *(beta)* — new plugin: a one-shot audit-and-tune skill that calibrates a
  repo's `CLAUDE.md`, verify loop, static guardrails, and permission allowlist to its house
  style (using the closest well-tuned sibling repo as the template). Three phases — discover →
  audit → propose-then-apply — with an `audit` keyword for report-only mode. The calibration
  counterpart to `evolving-claude-md`'s ongoing maintenance loop. Ships on the **beta**
  channel.

### Changed
- **beta marketplace.json** — switched to the explicit `{source: github, repo, path}` form
  (parity with stable's 2026-06-12 fix); older Claude Code CLIs (≤v2.1.153) reject the
  bare-string `pluginRoot`-relative shorthand.

## 2026-06-13

### Removed
- **brainstorm-panel 1.1.2** / **research-sweep 1.1.2** / **dev-crew 1.1.1** — all references to the
  **Fable** model tier (the opt-in Fable suggestion at the roster checkpoint; the architect/lead
  Fable-eligible flags + escalation policy in dev-crew; the conductor-never-on-Fable rule; the design
  doc `docs/decisions/2026-06-12-fable-model-selection.md`). Reason: Anthropic suspended Claude Fable 5
  and Mythos 5 on 2026-06-12 in response to a US government export-control directive citing a potential
  jailbreak; the timeline for restoration is unclear. Issue #8 is parked. Re-add when Fable returns.

## 2026-06-12 (later)

### Added
- **brainstorm-panel 1.1.1** / **research-sweep 1.1.1** — the roster checkpoint now emits an opt-in
  **Fable suggestion** grounded in the orchestrator's bottleneck: the panel (generation-bound) recommends
  one deep "visionary" generator seat on Fable (rest stay Opus for diversity); the sweep
  (verification-bound) recommends the skeptic-verifier (+ optional synthesizer) on Fable, scouts stay
  Opus. Never default. Design rationale: `docs/decisions/2026-06-12-fable-model-selection.md` (issue #8).
- README **"The Role System"** section — the four role-system plugins (`roles` + the three orchestrators)
  presented as a dedicated block, not just rows in the catalog.

## 2026-06-12

### Added
- **roles 1.0.0** — new plugin: a per-repo repository of *evolving roles* (`.claude/roles/`) usable
  four ways — solo (`/roles:as <role>` + per-persona skills), as dev-crew roles, brainstorm-panel
  seats, and research-sweep coverage roles. Ships seed personas (`architect`, `builder`, `debugger`,
  `optimizer`, `reviewer`, `refactorer`, `skeptic`), a SessionStart index + graduation-audit hook,
  and the shared-core convention. Absorbs the former `senior-prompts` beta plugin.
- **research-sweep 1.1.0** — joins the role system as the **"discover"** orchestrator: coverage-roles
  registry `.claude/roles/research.md`, dynamic angle composition from the information space, archetype
  coverage roles (`entity-scout`, `timeline-scout`, `source-scout`, `container-scout`) + probationary
  minting, a shared `skeptic` verifier + a synthesizer, and per-repo learning.
- **dev-crew 1.1.0** — escalation protocol (`BLOCKED` handoff + diagnosis-driven ladder), a
  machine-enforced phase-gate hook, handoff discipline, qa verify-against-reality, a `ui-reviewer`
  candidate role, and an axis-driven roster compose path.
- **brainstorm-panel 1.1.0** — a panel roles registry (`.claude/roles/panel.md`), skeptic seated by
  default, a unanimity→steelman guard, a 1-round default, pre-proposed practitioner/buildability seats,
  acceptance re-review, evidence capture, prefs-outrank-veto, and adaptive stopping.
- In-depth **Role System** architecture documentation; a naming convention for plugins and roles
  (documented in `CLAUDE.md`); a **Provenance & attribution** section in the README.

### Changed
- **Renamed** `parallel-research-sweep` → **`research-sweep`** (drop the redundant qualifier; join the
  crew/panel/sweep family).
- **Renamed** role personas to crew-aligned nouns: `build-app`→`builder`, `system-design`→`architect`,
  `debug-root-cause`→`debugger`, `optimize-perf`→`optimizer`, `understand-refactor`→`reviewer`,
  `clean-arch`→`refactorer`; coverage roles `by-*`→`*-scout`.
- **dev-crew** description reframed: the crew composes a *task-fit roster* to deliver a target —
  `architect → dev → qa → deployer` is one example lineup, not the definition.
- Read-only correctness: evolving plugins write state to the consuming repo's `.claude/` (or user
  memory), never into the read-only plugin cache; shipped `roles.md`/`log.md` are read-only seeds.

### Promoted
- **roles** promoted from the beta channel straight to the stable catalog (1.0.0).

## 2026-06-11

### Added
- Initial marketplace scaffold: `.claude-plugin/marketplace.json`, the `plugins/` layout, a jq-based
  validator, `Makefile`, CI (`validate.yml`), MIT `LICENSE`, and the Antora docs component (`docs/`).
- Stable plugins, all **1.0.0**: `evolving-claude-md`, `dev-crew`, `brainstorm-panel`,
  `learn-on-failure`, `implement-issue`, `maven-quality`, `security-audit`, `review-agents`,
  `parallel-research-sweep`.
- **Beta channel** (`alexmskills-beta` under `beta/`) with `make new-beta` / `make promote` tooling,
  and the `senior-prompts` beta plugin (later absorbed into `roles`).
- Trigger samples and copy-paste install blocks across the README and docs.
- The repo **dogfoods** `evolving-claude-md` on its own `CLAUDE.md`.
