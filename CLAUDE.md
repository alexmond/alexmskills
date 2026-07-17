# alexmskills

A public [Claude Code](https://code.claude.com) **plugin marketplace** of reusable, self-improving
skills and agents. Each skill is an independently versioned plugin. This file is the project's working
memory; the README is the public front door.

## Layout

```
.claude-plugin/marketplace.json   # the catalog — every plugin + its source/version
plugins/<name>/                   # one directory per plugin
  .claude-plugin/plugin.json      #   manifest (name, version, author, …)
  skills/<skill>/SKILL.md         #   one or more skills
  agents/<agent>.md               #   subagents (review-agents, dev-crew)
  hooks/hooks.json                #   plugin-shipped hooks (evolving-claude-md)
docs/                             # Antora component → published at alexmond.org/alexmskills
scripts/validate-marketplace.sh   # jq-based validator (also run in CI)
Makefile                          # validate / list / bump helpers
.claude/                          # this repo dogfoods evolving-claude-md on its own CLAUDE.md
```

## Catalog (see README for descriptions)

`evolving-claude-md`, `dev-crew`, `brainstorm-panel`, `learn-on-failure` (self-learning) ·
`implement-issue`, `maven-quality`, `security-audit` (workflow) · `review-agents` (review) ·
`research-sweep` (research).

## Conventions

- **One skill = one plugin**, unless skills are tightly coupled (then bundle + version them together,
  like `maven-quality`). This is what makes per-skill versioning possible at all.
- **Every `plugin.json` carries the same metadata shape**: `name`, `description`, `version` (semver),
  `author` (Alex Mondshain / alexmond@gmail.com), `homepage`, `repository`, `license: MIT`, `keywords`.
  The `name` MUST match its `marketplace.json` entry.
- **Bump versions with `make bump PLUGIN=<n> VERSION=<x.y.z>`** so `plugin.json` and `marketplace.json`
  never drift. Validate with `claude plugin tag --dry-run plugins/<n>`.
- **Run `make validate` before committing.** CI runs it too.
- **Skills must be project-agnostic.** No hardcoded absolute paths, usernames, or repo names — these
  are pulled FROM other repos and generalized; keep them that way.
- **Docs are part of "done":** a new plugin needs a `docs/modules/ROOT/pages/<n>.adoc` page + a
  `nav.adoc` entry, and every plugin version bump gets a `CHANGELOG.md` entry (grouped by date,
  tagged with the plugin + version).
- **Plugin naming:** orchestrators are `<scope>-<team-noun>`, the team-noun encoding coordination
  (`crew` = handoff/deliver, `panel` = debate/decide, `sweep` = fan-out/discover); other skills are
  descriptive kebab-case, verb-first for actions, ≤3 words, no redundant qualifiers.
- **Role naming:** a role is named for the *persona* (a noun — who they are), never the *task* (a verb
  — what they do), so it reads right seated solo, in a crew, on a panel, or in a sweep. Coverage roles
  use `<dimension>-scout`. Role names are shared across orchestrators (one `skeptic`, one `architect`).
- **Never push or cut release tags without explicit user confirmation.**
- **Attribution:** all plugins are original work by the author (MIT, per plugin.json `author`);
  the roles-plugin personas credit `@nahidulislam404`'s prompt thread as inspiration. This is
  a public-repo provenance note; don't drop it in a cleanup.

## Gotchas (load-bearing)

- **Evolving plugins must write state OUTSIDE their own dir.** A marketplace-installed plugin lives in
  a read-only cache (`~/.claude/plugins/cache/…`), so all mutable state goes to the consuming repo's
  `.claude/` (e.g. `.claude/roles/`, `.claude/dev-crew/log.md`) or user memory. Shipped `roles.md` /
  `log.md` are read-only *seeds*; the conductor copies them into `.claude/` on first run.
- **Local-directory marketplace install is unsupported by the CLI** (v2.1.173: "source type your
  Claude Code version does not support"). The marketplace still *parses/lists* locally; full install
  works once pushed to GitHub. Test a plugin locally with `claude --plugin-dir ./plugins/<n>`.
- **`evolving-claude-md` scripts read `CLAUDE.md` from CWD.** As a plugin they wire hooks via
  `${CLAUDE_PLUGIN_ROOT}` in `hooks/hooks.json`; a manual install points `.claude/settings.json` at
  `.claude/skills/evolving-claude-md/`. Hooks need a session restart to register.
- **Antora component version is `~` (versionless)** → clean `/alexmskills/` URL with no version
  segment. The site is built/deployed by `alexmond.github.io`, not this repo.
- **The PreToolUse lint hook enforces the D&L entry format** on any CLAUDE.md edit (date, **topic-tag**,
  ≤200 chars). Malformed entries are rejected — fix and retry.
- **No separate beta channel.** In-progress plugins live in the stable catalog with a `-beta`
  suffix in the name (e.g. `prompt-coach-beta`). Graduation renames the directory + updates
  `marketplace.json`. The two-marketplace setup was retired 2026-07-02 after too many CLI edge
  cases (bare-string source resolution vs clone root, `sparsePaths` ignored, dual `marketplace.json`
  confusing install vs reload, `extraKnownMarketplaces` schema drift).

## How this file evolves (learning mechanism)

This repo runs the `evolving-claude-md` skill on itself. Append to **Decisions & Learnings** whenever:
a non-trivial decision is made, the user gives durable feedback, a non-obvious gotcha appears, a
convention is set/revised, or scope shifts. Format below; lead with the *why*. Don't log routine
changes or anything obvious from the code. Strike through (`~~…~~`) on reversal; graduate a stable
topic (3+ entries, ≥14 days) into **Conventions**/**Gotchas**; archive quarterly with
`archive-decisions.py`.

### Decisions & Learnings (Recent — last 14 days)

> Format: `- YYYY-MM-DD — **topic-tag** — body ≤200 chars. Why: reason.` Enforced by the PreToolUse
> lint hook; audit runs on SessionStart + PostCompact.

- 2026-07-17 — **coach-docs-generated** — 0.48.1: doc audit vs code (nudge_style/counts/tiers/mastery were stale) + gen-rules-doc now injects summary + config-key ref blocks, harness drift-checked. Why: docs drifted; generate from data.
- 2026-07-17 — **coach-command-routing** — 0.48.0: +3 L5 rules routing native cmds (recurring->/schedule|/loop --interval, poll-until->/loop, outcome->/goal). 42 rules/positives co-fire. Why: coach didn't know the orchestration commands.
- 2026-07-17 — **coach-sources-tab** — 0.48.0: dashboard Sources tab - 127 citations deduped + ranked by importance (official>canon>practitioner, then cite-count) via _sources_section. Why: asked to surface sources prioritized.
- 2026-06-21 — **research-sweep-learning** — 1.1.3 adds per-run log, thin-agent diagnosis (slice vs agent), demote/retire rule, `## Research sweep` graduation block. Why: closes the only orchestrator without a log.
- 2026-06-26 — **evolve-audit** — 1.1.0 adds whole-file size check (25/40 KB), self-report on missing D&L heading, staleness trigger (closes #16). Why: siblings hit size cap; audit stayed silent.
- 2026-06-27 — **evolve-merge** — 1.1.1 adds *merge same-session clusters* as 4th downward pressure (works pre-14-days when graduation+archive blocked). Why: audit can recommend with no available action.
- 2026-06-27 — **screenshot-tour** — 1.0.0 new plugin: discover → plan → capture → assemble a deck under `presentation/`; driver-agnostic. Why: no product-tour skill existed.
- 2026-06-29 — **graduation-layers** — panel/crew 1.2.0 + roles 1.1.0: 3-layer split (registry / shared core / CLAUDE.md repo facts) + `/roles:evolve`. Why: flat graduation broke the role-substrate.
- 2026-06-29 — **auditable-unanimity** — panel 1.2.1: require `Steelman:` field on R1-unanimous runs (closes #25). Why: 47-run audit showed 30% R1-unanimous, 0 steelmans logged — guard invisible.
- 2026-06-29 — **marketplace-source** — migrated 12 plugins from broken `{github,path}` to `"./plugins/<name>"` (closes #28). Why: `github` source silently ignores `path`; install was a no-op for every external user.
- 2026-07-02 — **beta-source-clone-root** — bare-string plugin sources resolve from CLONE ROOT, not the marketplace.json parent (fossil; beta channel retired same day). Why: subdir install failed silently.
- 2026-07-03 — **prompt-coach-evolution** — full v0.1→v0.18 narrative at docs/decisions/2026-07-03-prompt-coach-evolution.md. Compacts 20 D&L entries. Why: 2-day cluster was overflowing D&L.
- 2026-07-03 — **prompt-coach-options-mastery** — 0.19.0: `:config options <key>` (per-choice explanations); `quick`/`full` interactive flows via AskUserQuestion; `mastery` dashboard + `mastery-reset[-all]`. Why: discoverability + reset path.
- 2026-07-03 — **prompt-coach-anthropic-align** — 0.20.0: 6 new rules (xml-tags/classical-role/test-goalseeking/verify-claim/overthinking/edit-preference) + `anthropic_ref` field + `:config sources` verb. 25/34 rules linked. Why: audit-driven coverage.
- 2026-07-03 — **prompt-coach-daily-review** — 0.21.0/0.22.0: `/prompt-coach-beta:daily-review` reads every repo's log.md + watermark for "since last review". Superseded by log-review skill (0.23.0). Why: cross-repo temporal analytics.
- 2026-07-03 — **log-review-extract** — 0.23.0: daily-review moved to `~/.claude/skills/log-review/`. Redacted by default; watermark auto-migrates. Why: coach output shouldn't leak repo names to GitHub.
- 2026-07-04 — **prompt-coach-picker-skip** — 0.24.0: reads session transcript, skips AskUserQuestion answers + `?`/`:`+list prefills. 17/17 real turns caught. Why: picker answers can't be rephrased to dodge a rule.
- 2026-07-04 — **prompt-coach-quickstart** — 0.25.0: Quick Start section added to SKILL.md + Antora page + help card intro. Covers install, nudge preview, 4 commands, say-it phrases. Why: new users needed onboarding path.
- 2026-07-04 — **prompt-coach-mastery-cmd** — 0.26.0: top-level `/prompt-coach-beta:mastery` + analysis (well-tested/barely-tested/untested + close-to-mastery). 18/29 real masteries flagged as untested. Why: discoverability + audit.
- 2026-07-04 — **prompt-coach-inactive** — 0.27.0: `min_fires_for_mastery` + new `inactive` status + graduation events in log + auto-migration. Legacy false-masteries move to `inactive`. Why: evidence-based mastery.
- 2026-07-04 — **prompt-coach-tips** — 0.28.0: 6 proactive tips (💡) — Mode A (matching) + Mode B (graduation-unlock paired to L1 masteries). Rate-limited variable-ratio; enabled by default. Why: advanced-technique nudging.
- 2026-07-04 — **prompt-coach-inline-only** — 0.29.0: `nudge_style` deleted, rendering always inline, new master `enabled: bool`. Legacy configs silently ignored. Why: 3 of 4 modes were dead surface.
- 2026-07-04 — **prompt-coach-collaborator** — 0.34.0: coach_style=collaborator (C+D). Hook tells Claude via additionalContext to rewrite the user's prompt in-place; no external API. `nudge` legacy path preserved. Why: nagger → collaborator.
- 2026-07-05 — **prompt-coach-liveness** — 0.35.0: praise had no inline branch (dead since v0.29); restored it + 🎓 mastery congrats + `ack_clean` clean-prompt heartbeat; fixed v0.34 fires_total double-count. Why: "too silent" was real.
- 2026-07-05 — **prompt-coach-access** — 0.36.0: `show_source_urls` (clickable doc URLs in coach block, in quick-set) + `sources --open` browser + new `paths` verb (skill folders, state, runnable scripts). Why: access to docs + own files.
- 2026-07-05 — **prompt-coach-analyze** — 0.37.0: on-demand `analyze "<text>"` / `--last N` + `/prompt-coach-beta:analyze` runs full 34-rule catalog on any prompt/history, coached. Why: knowledge on demand, not passive.
- 2026-07-05 — **prompt-coach-collab-only** — 0.38.0: removed legacy `nudge` mode + `coach_style` + 16 dead fns + voice/anti-habituation cfg (~570 lines); added `make test-coach` (15-check harness). Why: collaborator won; need a gate.
- 2026-07-05 — **prompt-coach-variants-gone** — 0.38.1: stripped ~200 dead nudge strings — `nudge={}` from all 34 rules + field + 5 accessors (AST-span). analyzer 4292→3835 lines; harness 15/15. Why: collaborator writes fresh.
- 2026-07-05 — **prompt-coach-incremental-routing** — 0.39.0: L5 rule (35 total) — terse per-step routing ("one after another") → batch into TaskCreate/Workflow. Research-backed; harness 16/16. Why: user routes a lot; fell between conversational-skip and verbose L5 regexes.
- 2026-07-05 — **prompt-coach-earned-mastery** — 0.40.0: mastery driven by *demonstrations* (positive-detector fires = you USED the technique), not clean-streak absence. +13 positives (35/35), grandfather migration, harness 18/18. Why: rules mastered unexercised.
- 2026-07-06 — **prompt-coach-reset-fix** — 0.40.1: mastery-reset now zeros `demonstrations` + drops `mastery_basis` (was preserving them → reset rule instantly re-mastered). Harness 19/19. Why: v0.40 made demonstrations the driver; reset helper predated it.
- 2026-07-06 — **prompt-coach-adaptive** — 0.41.0: 3 research-backed features on a shared ledger — P1 acceptance loop (accept/edit/reject), P2 precision-gated activation + fatigue cap, P3 decaying mastery (watch tier, expanding review). Harness 23/23. Why: telemetry showed 0 acceptance tracked, mastery starving.
- 2026-07-07 — **prompt-coach-ack-specific** — 0.41.1: clean-prompt ack names the rule (`you used <rule>` / `watching for: <rule>`) instead of "watching N rules". Harness 24/24. Why: user feedback — bare count told them nothing.
- 2026-07-07 — **prompt-coach-acceptance-quality** — 0.42.0: acceptance signal made trustworthy + visible — #0 attribution (credit primary rule only), #1 blind-reject filter, #2 `config acceptance` verb. Ack "all mastered" → "coaching quiet — N/35 mastered". Harness 27/27. #3 downstream-quality → GitHub issue.
- 2026-07-15 — **roles-library-anchors** — roles 1.2.0 + coach 0.47.1: each persona anchored to a Prompt Library category (reviewer->Review etc.); role.md Body names it, /roles:as step 2.5 consults it, role-system.adoc maps it; coach library verb gained --category/--role. One-way optional link (roles never hard-deps coach; degrades silently). Why: fold library into roles without coupling.
- 2026-07-15 — **coach-prompt-library** — 0.47.0: vendored Anthropic Prompt Library (52 gold prompts) as offline snapshot; stdlib keyword matcher; /library cmd + config verb + dashboard tab; library_hints grounds rewrites; audit-library.py calibration (make library-audit); fixed vague-reference FP on demonstrative+noun (clean 27->31%). Why: coach goes generative + self-calibrates.
- 2026-07-14 — **coach-new-rules-from-sources** — 0.46.0: mined 3 rules from the researched docs (36->39): untrusted-content-execution (L3, injection), speculative-generality (L4, YAGNI), premature-abstraction (L6). Each grounded (fire+veto+FP tested), mirror positive, RULE_HELP, harness. Why: new sources surfaced uncovered principles.
- 2026-07-14 — **coach-source-variety** — 0.45.0: wide per-tier web sweep added citations 90->178 (all curl-verified live); 8 anchorless rules prioritized (5-6 each); centralized in one _EXTRA_SOURCES block appended post-catalog (Rule() defs untouched). Why: catalog shouldn't be opinion-of-one.
- 2026-07-14 — **coach-rules-doc** — 0.44.1: Antora per-rule reference generated from build_dashboard (gen-rules-doc.py --inject) - catches + bad->good + exact links; +missing-guardrails anchor; 26 URLs verified live; harness 37. Why: docs now match the dashboard, links precise.
- 2026-07-10 — **orchestrator-usage-sequence** — new Usage sequence section in role-system.adoc: chooser table, discover/decide/deliver hand-offs, worked example; xref'd from all 3 skill pages. Why: differences were documented, the sequence wasn't.
- 2026-07-10 — **coach-workflow-verify-rule** — 0.43.0: L5 rule workflow-fanout-no-verify (36 rules); discovery fan-out with no verify pass; mirror positive asked-fanout-verify; harness 28/28. Why: coach nudged toward Workflow, not verifying it.
- 2026-07-10 — **coach-collaborator-honesty** — 0.43.0: collaborator_gate config (default false = honest 'proceeding' + names which prompt was used; true = stop & wait). Why: block said 'reply yes to proceed' but never waited and hid the prompt used.
- 2026-07-14 — **coach-web-dashboard** — 0.44.0: stdlib-only local web dashboard (serve.py on 127.0.0.1) + config.py build_dashboard/api_set/api_action + dashboard verb; stats, mastery+URLs, live config editor. Harness 30/30. Why: UI view/edit over existing state, zero deps.
- 2026-07-14 — **coach-dashboard-polish** — 0.44.0 UI: multi-page toolbar + level TOC + per-rule progress bars + obj sub-field editor + RULE_HELP (plain catches + bad/good example per rule) + bluish theme. Optional Playwright test (make test-dashboard, skips if absent). Harness 31/31. Why: guidance was Claude-facing; UI needed structure.

### Historic (older than 14 days · see git log for the build-up)

- 2026-06-11 — **project-goal** — host reusable, self-learning Claude Code skills as a versioned marketplace with Antora docs.
- 2026-06-11 — **marketplace-shape** — one plugin marketplace, per-plugin versioning; details graduated to Conventions/Gotchas. Why: Claude Code versions per plugin.
- 2026-06-12 — **ecosystem-review** — 1.1.0 improvement plan → docs/decisions/2026-06-12-ecosystem-review.md. Why: benchmark before iterating.
- 2026-06-12 — **role-system-shape** — role system first-class across crew/panel/sweep; details graduated to Conventions. Why: unify role vocab.
