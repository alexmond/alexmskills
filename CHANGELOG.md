# Changelog

All notable changes to the **alexmskills** marketplace and its plugins.

Plugins are versioned **independently** — the authoritative version is each plugin's `plugin.json`.
This log groups changes by date and tags each entry with the plugin and the version it shipped in.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/); the marketplace itself is
unreleased/rolling (no global version).

## 2026-06-29 (later)

### Changed
- **brainstorm-panel 1.2.1** (closes #25) — make the unanimity guard *auditable*. Audit across
  47 panel runs in 5 sibling repos found that 30% of runs were round-1 unanimous but **0 logs
  ever recorded the steelman guard firing** — the 1.1.0 anti-groupthink remedy was invisible
  in practice. Two changes:
  - Log entry template now requires a `Steelman:` field whenever R1 was unanimous, with one of
    four outcomes (`ran, opposing view was X — retained | adopted | panel reversed` /
    `waived because <reason>` / `n/a — pushback present in R1`). Silent unanimity is now
    indistinguishable from groupthink and must be called out.
  - SKILL.md prose reframed: unanimity is a **risk signal**, not a positive outcome to
    celebrate. New log wording: *"5/6 aligned — note: low dissent; opposing view considered
    was Y"* over the older *"strong cross-role convergence"*.
  - Anti-anchoring (seats see only the question in R1, no prior synthesis — `affaan-m/ECC
    council` mechanism) is **deferred**, contingent on a revalidation pass after 10+ new runs
    with the auditable guard. Goal is the cheapest fix that turns invisible-guard into evidence.

## 2026-06-29

### Changed
- **brainstorm-panel 1.2.0** / **dev-crew 1.2.0** — graduation now routes to the right layer of
  the role substrate, not flat into CLAUDE.md. Three-layer split is now explicit in both SKILL.md
  files:
  - **Per-role wisdom** (how the role *behaves in this orchestrator*) → the role's row in
    `.claude/roles/{panel,crew}.md`.
  - **Cross-context wisdom** (true in panels + crew + sweep + solo) → graduation *candidate*
    for the shared core role file `.claude/roles/<role>.md` `## Learnings (core)` (user-gated;
    only when the `roles` plugin is installed).
  - **Repo facts about seating** (always seat X here; default lineup per category) → the small,
    terse `## Panel roles` / `## Dev crew` block in `CLAUDE.md` — *not* the place for per-role
    wisdom or generalized lessons.

  Why: a sibling-repo audit found that flat graduation to CLAUDE.md was leaving per-role wisdom
  invisible to the orchestrators that don't seat the role first, defeating the shared-role-
  substrate premise. Discovered by `unitrack`'s Restraint Skeptic (5×+) and QA/SDET (4×+) never
  lifting, and `builder`'s UI-five roster (6×+) never lifting — all because the only documented
  destination was the wrong layer.

### Added
- **roles 1.1.0** — new sub-skill `/roles:evolve` that closes the "graduation gets a learning
  *in*, but nothing keeps the role file useful *after*" gap. Audits each role file across four
  dimensions: *consolidation* (≥3 Learnings entries on one topic → propose merge),
  *staleness* (Learnings citing files/symbols no longer in the tree, excluding `.claude/roles/`
  itself to avoid self-reference false positives → propose strike), *body-drift* (≥3 core
  learnings contradict the Charter/Body → propose refresh), and *solo→core graduation*
  (≥3 solo entries on one topic + role used by ≥2 consumer registries → propose lift). Engine
  is `scripts/evolve-roles.py` — pure regex + `git grep`, no LLM, wall-clock budget-capped
  (~4s). All proposals user-gated; never silently rewrites a role file. Complements the
  existing reactive SessionStart `roles-init-audit.py` hook with an actionable deep pass.

## 2026-06-27 (later)

### Added
- **screenshot-tour 1.0.0** — new plugin: build a presentation-ready screenshot deck of the
  current product for demos, slide decks, and stakeholder walkthroughs. Three phases:
  *discover* (read README + entry points + `--help`/routes + recent CHANGELOG → propose 5–12
  numbered aspects in `presentation/plan.md`, user-gated), *capture* (one recipe per aspect
  under `presentation/recipes/`, using the right tool per surface — the project's existing
  browser driver for web (defaults: Selenium-Java for JVM repos, Playwright for Node/Python),
  Charmbracelet VHS for CLI/TUI, Charmbracelet Freeze for code and output stills, manual
  fallback for OS dialogs / mobile / hardware), *assemble* (captioned narrative-ordered
  `presentation/tour.md`, optional ImageMagick contact sheet). Self-learning via
  `.claude/screenshot-tour/log.md` → graduates stable invariants into a `## Screenshot tour`
  block in the repo's `CLAUDE.md`. Slide-deck export, README integration, and docs-site
  embedding are opt-in follow-ups, not the default.

## 2026-06-27

### Added
- **evolving-claude-md 1.1.1** — adds **merge** as the fourth downward pressure in SKILL.md,
  closing a loop gap discovered while dogfooding: when CLAUDE.md hits the audit's "compaction
  RECOMMENDED" level but every entry is <14 days old, graduation (needs 14-day stability) and
  quarterly archive (needs an old-enough cutoff) are both blocked. Merge collapses same-session
  same-area clusters (phased rollouts like `e2a` / `e2b` / `e3` / `e4`; multi-aspect bursts
  within ~48h) into one consolidated entry without claiming the pattern has stabilized — keeps
  the load-bearing whys, splits per-aspect detail out to `docs/decisions/{date}-{topic}.md` if
  still wanted, and is reversible (split a sub-decision back out via strike-through follow-up
  if it evolves independently). Discovered while compacting `jvmlens`'s 37-entry / 25 KB log.

## 2026-06-26

### Added
- **evolving-claude-md 1.1.0** — three audit upgrades after a sibling-repo survey found that
  none of the live CLAUDE.md files were triggering compaction even though most were past the
  Claude Code whole-file size pressure. Three changes:
  - **Whole-file size check** in `audit-claude-md.py` (warn 25 KB, recommend 40 KB) — the
    actual context-pressure dimension. Catches bloat that lives outside `### Decisions &
    Learnings` (Conventions / Architecture / Gotchas / Changelog) which the entry/line
    counters never saw.
  - **Self-report when D&L is missing** — a CLAUDE.md without the section no longer exits
    silently; the audit reports total file size + dated-bullet count and recommends wiring
    `evolving-claude-md`. This is what was hiding the bloat in repos like `builder`.
  - **Staleness trigger** (closes alexmskills#16) — extracts backticked artifact-looking
    tokens (paths, `ClassName.method`, `--cli-flags`, `<xml-tags>`, known-extension
    filenames) from each entry, runs `git grep -qF` against the tree, flags entries citing
    ≥2 missing tokens. Wall-clock-budget-capped (~2.5s) so the hook stays under its
    timeout. Gives the loop a *delete* lever, not just a *compress* lever.

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
