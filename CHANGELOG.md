# Changelog

All notable changes to the **alexmskills** marketplace and its plugins.

Plugins are versioned **independently** — the authoritative version is each plugin's `plugin.json`.
This log groups changes by date and tags each entry with the plugin and the version it shipped in.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/); the marketplace itself is
unreleased/rolling (no global version).

## 2026-07-02 (latest)

### Changed
- **prompt-coach-beta 0.6.0** — two behavior changes based on real-session feedback:
  - **Conversational short-circuit.** Many prompts are approvals (`sure`, `publish`,
    `go`, `ship it`), multi-choice picks (`1 and 2`, `a and b`, `option a`), or
    continuations (`continue`, `next`, `thanks`). The rules misfire on these and the
    typo normalizer over-corrects short conversational words (`publish` → `polish` at
    edit distance 2, then the coach nags about refinement). A new `is_conversational()`
    heuristic detects them BEFORE any rule matching / normalization and skips analysis
    entirely — prompt is logged with `outcome: skipped:conversational` for audit, but
    doesn't touch streaks, cooldowns, or praise counters. Same "approvals aren't the
    signal" principle as GitHub PR-approval comments not counting toward review-count
    metrics.
  - **`praise_ratio` default 10 → 3.** The 1-in-10 default was Kohn-inspired
    (don't-dilute-the-correction), but that's a steady-state value. During trial you
    need to see the encouragement layer *fire* to know it works at all. 3 is trial-
    friendly; bump to 8–10 in config once the layer has proved itself (a week of use).

## 2026-07-02 (later)

### Changed
- **Retired the beta channel entirely.** The `alexmskills-beta` marketplace
  (previously at `beta/.claude-plugin/marketplace.json`) is gone. In-progress
  plugins now live in the single stable marketplace with a `-beta` suffix in
  the name — the current examples are `prompt-coach-beta` (0.5.0) and
  `tune-repo-beta` (0.1.1). Same catalog, same install command, obvious at a
  glance that it's beta quality.
- **Why the pivot.** The two-channel setup kept hitting edge cases in the
  Claude Code CLI — bare-string plugin sources resolved from clone root vs
  marketplace-parent (fine for stable, broken for beta); `sparsePaths` not
  honored; dual `marketplace.json` at repo-root vs subdir confusing install
  vs `/reload-plugins`; `extraKnownMarketplaces` requiring per-user opt-in
  with a moving schema (`git-subdir` → `github` + path → `url`) — each
  workaround caught a class of user error but the surface area kept growing.
  One channel + a suffix convention removes every one of them.
- **Install path for beta plugins is now identical to stable.** No
  `extraKnownMarketplaces`, no `git-subdir` gymnastics — just:

  ```
  /plugin marketplace add alexmond/alexmskills
  /plugin install prompt-coach-beta@alexmskills
  ```

- **`make graduate PLUGIN=<name>-beta`** replaces `make new-beta` +
  `make promote`. Renames the directory (drops the `-beta` suffix),
  updates the plugin.json name, and rewrites the marketplace entry (drops
  the `beta` category + keyword). Follow with `make bump` to set a real
  release version.

### Removed
- `beta/` directory tree — the whole beta channel, README, and empty
  scaffold folders.
- `scripts/new-beta-plugin.sh` and `scripts/promote-plugin.sh` — replaced
  by `make graduate` for the one operation that survives.
- `extraKnownMarketplaces.alexmskills-beta` from `.claude/settings.json` —
  no separate marketplace to register.
- Beta-channel handling in `scripts/validate-marketplace.sh` — one channel,
  simpler validator.

## 2026-07-02

### Added
- **prompt-coach 0.5.0** (beta) — **typo tolerance**. A pre-pass normalizes each prompt against a
  curated set of ~90 trigger words drawn from the rule catalog, using a banded Levenshtein edit
  distance (custom, ~15 lines, zero deps). Dyslexic-friendly by design (Alex is dyslexic; this is
  the personal use case that motivated it). Only substitutes on a **unique** closest match, and
  uses **adaptive tolerance** (distance-1 for tokens ≤ 6 chars, distance-2 for longer) so
  short-word collisions like `public ↔ rubric` don't produce false corrections. Examples that
  get fixed: `refacotr` → `refactor`, `evrything` → `everything`, `veryfy` → `verify`,
  `cleanre` → `cleaner`. Every correction is logged (raw + corrected in `log.md`; per-word
  frequency in `state.json`).
- **Self-report / health metrics.** New `normalization_stats` block in global state tracks
  `prompts_with_corrections`, `tokens_corrected_total`, and per-word `top_corrections`. Rising
  numbers signal that the regex rules aren't covering the user's actual prompts and are worth
  tuning. A parallel `llm_fallback_stats` block is stubbed for the v0.6 opt-in fallback (same
  signal, one level up).
- **Config knobs**: `typo_tolerance` (int, default `2`; `0` disables the whole normalization
  pass), `llm_fallback` (nested object, `enabled: false` default; v0.6 stub).

## 2026-07-01 (latest)

### Added
- **prompt-coach 0.4.0** (beta) — encouragement layer + L6 skill-awareness.
  - **Encouragement**: 21 *positive detectors* mirror the negative rules and praise the specific
    positive behavior (not the absence of a negative), e.g. `stated-metric`, `stated-guardrails`,
    `provided-example`, `asked-plan-first`. Praise is *sparing* — default 1-in-10 clean prompts
    (variable-ratio, per Skinner) + always on rule mastery + always on first-after-fire
    (immediate correction after being nudged). Never emitted on a prompt that also got a nudge
    (Kohn 1993). 2–3 rotated phrasings per positive with a light touch of warmth/humor. Config:
    `praise_ratio` (default 10), `praise_on_mastery` (default true),
    `praise_on_first_after_fire` (default true), `disable_praise` (default false). Grounded in
    Mueller & Dweck 1998 (process praise > trait praise), Fogg 2019 (celebration → habit),
    Brophy 1981 (functional analysis of teacher praise), Deci & Ryan 2000 (autonomy-supportive
    framing), Kohn 1993 (don't dilute the correction).
  - **L6 skill-awareness** (new tier, 3 rules): `no-skill-lookup` ("how do I X" without checking
    for an existing skill), `pattern-worth-abstracting` ("again / same as before" — rule of
    three), `no-skill-composition` (multi-step ceremony not named as a skill candidate). Plus
    2 positives: `invoked-skill` (used a slash-command / named a skill), `abstracted-to-skill`
    ("let's make a skill for this"). Grounded in Fowler *Refactoring* (rule of three), Kent
    Beck's YAGNI, Anthropic Claude Code Skills docs, McIlroy's Unix philosophy (composition),
    Norman *Design of Everyday Things* (discoverability > memorability).
- **Total catalog**: **27 rules across 6 tiers** + **21 positive detectors**. On the smoke-test
  suite (49 positive+negative fixtures across all new detectors), all pass.
- (v0.3 was folded into 0.4 — never externally released; single bump.)

## 2026-07-01 (later)

### Added
- **prompt-coach 0.2.0** (beta) — advanced-concept coverage. 13 new rules across three
  areas the v0.1 catalog missed:
  - **L3 classical prompting** (4 new): `no-few-shot` ("like X" without an example),
    `no-chain-of-thought` (why/debug/trace ask without "think first"), `no-rubric`
    (judgment ask without axes), `no-uncertainty-budget` (investigative ask without
    an "if unsure, say so" clause). Adds Wei et al. 2022 (CoT), Brown et al. 2020
    (few-shot), and Anthropic multishot/CoT docs to sources.
  - **L4 goals & loops** (new tier, 3 rules): `implicit-goal` (action without a
    stated outcome/why), `unbounded-iteration` ("keep improving" without a stopping
    condition), `no-rubric-for-refine` (refinement without naming which axis).
  - **L5 Claude-Code tool-native** (new tier, 6 rules): `no-plan-mode-for-risky`,
    `no-task-list-for-multi-step`, `no-agents-for-parallel-lookup`, `no-role-for-critique`,
    `no-panel-for-contested-design`, `no-workflow-for-fanout`. These nudge you toward
    your own tool chest (Plan mode, TaskCreate, parallel Explore/Agent, /roles:as,
    brainstorm-panel, Workflow) when the prompt shape calls for it.
- Total catalog: **24 rules** across 5 tiers. `max_active_rules=5` still caps how many
  can nag at once — L1 masters first, then L2 rules slot in, and so on. On the
  smoke-test suite (26 positive+negative fixtures for the new rules), all 26 pass.

## 2026-07-01

### Added
- **prompt-coach 0.1.0** (beta) — new plugin in the `alexmskills-beta` channel. A
  `UserPromptSubmit` hook analyzes every prompt sent to Claude Code against a tiered ruleset of
  prompting best practices (L1 fundamentals: vague-reference, no-definition-of-done,
  unbounded-scope, improve-without-metric, missing-guardrails; L2 intermediate: compound-tasks,
  no-verify-loop, missing-context-fetch, no-format-spec; L3 advanced: no-adversarial-check,
  retry-without-diagnosis). One nudge per prompt, per-rule cooldowns, tier-progressive graduation:
  a rule masters after N clean prompts in a row (default 15), which activates the next dormant
  rule. Rules cite ≥2 sources drawn from Anthropic prompt engineering docs, Claude Code best
  practices, OpenAI's prompt engineering guide, Simon Willison's notes, and *The Prompt Report*
  (Schulhoff et al., 2024) — see [`docs/sources.md`](beta/plugins/prompt-coach/docs/sources.md).
- **Nudge style is configurable**: `both` (stderr box + `additionalContext` for Claude; default),
  `silent` (Claude only), `log-only` (no output, log the fire). Config resolves local
  (`.claude/prompt-coach/config.json`) → global (`~/.claude/prompt-coach/config.json`) → default.
- **State: global mastery + per-repo overrides**. Global ledger at
  `~/.claude/prompt-coach/state.json` tracks fires and mastery across every repo; local state at
  `.claude/prompt-coach/state.json` records per-repo fires and lets a repo *reactivate* a globally
  mastered rule (e.g. the rules that stayed on for a Java repo but should be re-taught in a docs
  repo).
- **Say-it affordances** for common toggles — *"coach pause 10"*, *"coach off vague-reference"*,
  *"set prompt-coach to silent"* — Claude edits the right config/state file. No slash commands
  yet; the SKILL.md documents the phrasing.
- **Non-blocking, deterministic, cheap.** Pure regex heuristics, no LLM call; runs in ~10 ms; if
  it errors, the hook prints the error to stderr and exits 0 so your prompt never gets blocked.

## 2026-06-29 (later 2)

### Fixed
- **marketplace.json source schema** (closes #28) — every plugin in both channels migrated from
  the silently-broken `{source: "github", repo, path}` object form to the canonical relative-path
  string form (`"./plugins/<name>"` for stable, `"./plugins/tune-repo"` for beta). The `github`
  source type **only supports `repo`, `ref`, and `sha`** — it silently ignores `path`, cloning
  the full repo and putting `installPath` at the repo root, where Claude Code then fails to find
  any plugin's `.claude-plugin/plugin.json` or `skills/`. Every external user who tried
  `/plugin install <name>@alexmskills` since the marketplace launched got a silent no-op
  install. Found by an external bug report (initially misdiagnosed as a CLI bug) traced back to
  upstream issue [anthropics/claude-code#43811](https://github.com/anthropics/claude-code/issues/43811)
  (closed by the original reporter as "user error, wrong source type"). Sampled 5 well-known
  public marketplaces (anthropics/claude-code, wshobson/agents, daymade/claude-code-skills,
  obra/superpowers, affaan-m/everything-claude-code) — every one uses the relative-path string
  form. We were the outlier.

### Changed
- **`scripts/validate-marketplace.sh`** — hard-fails on any plugin source that uses
  `{source: "github", path: <anything>}` to prevent the regression. Validator now teaches the
  correct alternative in the error message.

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
