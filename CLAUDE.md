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
.claude/                          # per-plugin state (mindmap, prompt-coach, skill-linter)
```

## Catalog (see README for descriptions)

`evolving-claude-md`, `memory-hygiene`, `dev-crew`, `brainstorm-panel`, `learn-on-failure`, `roles`, `prompt-coach`
(self-learning) · `implement-issue`, `maven-quality`, `security-audit`, `screenshot-tour` (workflow) ·
`review-agents` (review) · `research-sweep` (research) · `skill-linter` (self-learning). Beta (`-beta` suffix): `tune-repo-beta`, `systemic-fix-beta`.

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
- **Docs are part of "done":** a new plugin needs a `docs/modules/ROOT/pages/<n>.adoc` page, a
  `nav.adoc` entry **and a row on `index.adoc`**; every version bump gets a `CHANGELOG.md` entry
  (grouped by date, tagged with plugin + version). `make validate` enforces all three — it was a
  convention until the landing page drifted four plugins behind the catalog.
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
- **`evolving-claude-md` scripts read `CLAUDE.md` from CWD.** Hooks wire via `${CLAUDE_PLUGIN_ROOT}`
  in `hooks/hooks.json` and need a session restart to register. It is installed **globally** (user
  `~/.claude/settings.json`), so this repo's hooks run the *installed* build, not `plugins/` — test
  edits with `claude --plugin-dir ./plugins/evolving-claude-md`, and reinstall to pick them up.
- **Antora component version is `~` (versionless)** → clean `/alexmskills/` URL with no version
  segment. The site is built/deployed by `alexmond.github.io`, not this repo.
- **The PreToolUse lint hook enforces the D&L entry format** on any CLAUDE.md edit (date, **topic-tag**,
  ≤200 chars). Malformed entries are rejected — fix and retry.
- **No separate beta channel.** In-progress plugins live in the stable catalog with a `-beta`
  suffix in the name (e.g. `tune-repo-beta`). Graduation renames the directory + updates
  `marketplace.json` + drops the `beta` category/keyword (see `make graduate`; `prompt-coach`
  graduated 2026-07-28). The two-marketplace setup was retired 2026-07-02 after too many CLI edge
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

- 2026-08-18 — **ticket-triage** — 10 open issues assessed vs tree: #4 closed (invariant shipped as linter rule), #8/#31 fact-corrected, #32 re-run scheduled for Aug 22 (cloud reminder). Build order: #31 -> #34 -> #33 -> #30 -> #20 -> #8 -> #14/#3. Why: backlog rots like any log.
- 2026-08-18 — **local-skills-sweep** — 26 local skills linted, all owned findings fixed: 7 desc trims (spec cap), dual-mode learning state (screenshot-sweep+sb-k8s), collection budget 17.3k->under 15k. 3 linter FPs became refinements. Why: the budget overrun meant skills silently not triggering.
- 2026-08-18 — **type-aware-linting** — linter 0.4.0: skills classified by shape (workflow/orchestrator/learning/reference/scripted), rule pack per shape + hooks/commands/plugin-root surfaces. Why: an orchestrator and a reference file fail differently; one rulebook flags neither.
- 2026-08-18 — **researched-rules-not-invented** — linter 0.3.0: 87 claims -> 41 verified -> 14 rules, each cited; calibrated on 69 external skills (+20 warns, all true). 2 FP classes + 1 parser bug found by calibration, not review. Why: a rule without a source gets dismissed; one without calibration gets ignored.
- 2026-08-18 — **deep-review-sweep** — allowed-tools in agents is silently ignored (review-agents ran full-toolset since 1.0.0); linter 0.2.0 now lints agents; 4 harnesses into CI; 14 lint warns -> 1. Why: the linter's blind spot was exactly where the worst defect lived.
- 2026-08-17 — **thresholds-are-taste-until-configurable** — evolve 1.3.0: 11 thresholds now per-repo (defaults->global->repo), companion files (.claude.local.md + nested) size-checked, routing rule added. Why: defaults calibrated on one corpus are one person's taste imposed on everyone.
- 2026-08-17 — **coverage-is-the-upward-check** — evolve 1.2.0: audit only pushed content DOWN, so a file could pass every threshold and never name the build command. Gaps grounded in the tree, 0 fires on 29 repos. Cut the gotchas check at 59% fire rate. Why: measured, not reasoned.
- 2026-08-15 — **pmd-skill** — maven-quality 1.1.0: PMD split out of codestyle (style vs defects are different jobs). Ruleset+wiring grounded in real repos; triage by priority not count. Why: namespaced pmd.xml makes a naive findall report CLEAN on a failing project.
- 2026-08-13 — **lenient-parser-launders-input** — skill-linter's own frontmatter was invalid YAML (bare `word:` continuation) so it loaded with NO metadata; its hand-rolled parser called it clean. Why: a lenient stand-in for a strict parser is worse than no check. Pinned agreement with yaml.safe_load.
- 2026-08-13 — **role-system-docs-split** — 347 lines -> 3 pages (concept/usage/files). #usage-sequence moved, so 3 inbound plugin-page xrefs + 1 internal ref were repointed. Why: a moved anchor breaks silently — no build error, just a dead link.
- 2026-08-13 — **prompt-coach-docs-split** — 824-line page -> 4 (overview/rules/config/learning); gen-rules-doc targets one page per block and now FAILS on a skipped block. Why: a note that scrolls past is how a page loses its generated half.
- 2026-08-13 — **docs-coverage-gate** — index.adoc was 4 plugins stale + 4 pages orphaned; screenshot-sweep had no page. validate now checks page+nav+index per plugin, both directions. Why: a convention nothing checks rots silently.
- 2026-08-08 — **skill-linter** — 0.1.0 new plugin: SKILL.md conformance from skill-creator + skill-development + writing-skills, every rule cited in references/rule-sources.md. Why: the 3 sources conflict twice; resolved narrower than either.
- 2026-08-08 — **linter-credibility-is-the-constraint** — Half the harness asserts rules DON'T fire; fenced code and quoted user phrases are excluded after 2 real FPs. Why: noise kills a linter faster than a missed defect.
- 2026-08-18 — **systemic-fix-beta** — 0.1.0 new plugin (#14, agent-built from the 2026-06-14 design doc): bug = instance of a class; scope/class/prevention report BEFORE patching, default local-fix-only; per-repo calibration profile. Why: unguarded, the discipline degenerates into refactor sprawl.
- 2026-08-18 — **harvest-rung** — make harvest (#3): scans repos' .claude/roles learnings, clusters by role+overlap, drafts seed graduations at >=2-repo recurrence; PR stays the curation gate. Fleet truth: 27 bullets / 1 repo / 0 candidates. Why: harvest, don't sync.
- 2026-08-18 — **fable-tiers-armed** — panel 1.3.0 + sweep 1.2.0 (#8): registry rows gain model field; gated Fable at the bottleneck seat only (panel: one generator; sweep: verifier). Re-arms the 2026-06 suspension-withdrawn policy. Why: tier decisions should be durable, and Fable everywhere flattens diversity.
- 2026-08-18 — **tour-standardization** — screenshot-tour 1.1.0 (#20): host hygiene on every rendered surface (pixels beat text scanners), affordance-trap pre-check in plan.md, canonical attribution + footer-only repro + lead-with-3 subset. Why: two real decks diverged on exactly these.
- 2026-08-18 — **coach-friction-proxy** — 1.2.0 (#30a+c): accepted rewrite opens 3-prompt friction window (retry/recoach/complaint) + hollow-accept on original re-stated; superseded windows fold partial. #30b (A/B) deferred to MCP. Why: acceptance is adoption, not quality.
- 2026-08-18 — **memory-hygiene** — 0.1.0 new plugin (#33): eviction-by-wrongness for agent memory; vendored freshness core (harness pins copies identical); calibration 207->15 findings via pointer filters (--flags, foreign paths, ellipsis). Why: rot recalls false, bloat just ignores.
- 2026-08-18 — **freshness-core** — evolve 1.4.0 (#34): staleness -> 3 rot classes in vendorable freshness.py (vanished artifact, contradicted version pin, passed sequence fact). 29-repo calibration: 3 TP, 0 FP. Why: contradiction-grounding beats undated-claim heuristics.
- 2026-08-18 — **coach-eval-harness** — 1.1.0 (#31): eval_coach.py scores rule precision/recall vs hand-labeled golden.jsonl; gate at 0.80/0.60, n>=5. Baseline: no-verify-loop + implicit-goal 0.00 precision. Why: fast-filter FPs are now measured, not anecdotal.
- 2026-08-08 — **ai-grounding-is-prompt-not-context** — 0.2.1: ✦ returned any-codebase advice though CLAUDE.md was loaded all along. Fix was the prompt (name the repo, demand specifics) + treat the "Main idea" seed as blank. Why: context present != context used.
- 2026-08-08 — **mindmap-ai-expand** — 0.2.0: node -> `claude -p` in-repo, tools denied, map sent as context, preview before apply. Tests split by cost: stubbed in test-canvas, live in test-ai. Why: an idea expanded without its goal is generic.
- 2026-08-07 — **affordance-vs-mechanism** — 0.1.3: editing worked but looked impossible (dbl-click only, unsignposted). Added type-to-replace, click-again, per-node hint. Why: 13 UI checks tested the mechanism, never the affordance.
- 2026-08-07 — **mindmap-prompt** — 0.1.0 new plugin: offline canvas -> organized prompt. BFS spanning tree (not DFS) linearizes the graph; cross-links compile to refs. Saves JSON Canvas in .claude/mindmap/. Why: designed DFS was wrong, the golden fixture caught it.
- 2026-08-07 — **mindmap-skill-design** — Prior-art confirmed 25/25 -> BUILD: only ContextMinds + obsidian-llm-plugin do map->prompt, both unadoptable. Design doc dated 2026-08-07 in docs/decisions. Why: niche verified open.

### Historic (older than 14 days · see git log for the build-up)

- 2026-07-28 — **coach-collaborator-era** — v0.19→v0.49→1.0.0 in 25 days: collaborator rewrites, demonstration-earned mastery, acceptance ledger + precision gating, vendored library, web dashboard. 36 entries compacted to docs/decisions/2026-08-18-prompt-coach-v019-v049.md. Why: cluster outgrew the log.
- 2026-07-15 — **roles-library-anchors** — roles 1.2.0 + coach 0.47.1: each persona anchored to a Prompt Library category (reviewer->Review etc.); role.md Body names it, /roles:as step 2.5 consults it, role-system.adoc maps it; coach library verb gained --category/--role. One-way optional link (roles never hard-deps coach; degrades silently). Why: fold library into roles without coupling.
- 2026-07-10 — **orchestrator-usage-sequence** — new Usage sequence section in role-system.adoc: chooser table, discover/decide/deliver hand-offs, worked example; xref'd from all 3 skill pages. Why: differences were documented, the sequence wasn't.
- 2026-07-02 — **beta-source-clone-root** — bare-string plugin sources resolve from CLONE ROOT, not the marketplace.json parent (fossil; beta channel retired same day). Why: subdir install failed silently.
- 2026-06-29 — **graduation-layers** — panel/crew 1.2.0 + roles 1.1.0: 3-layer split (registry / shared core / CLAUDE.md repo facts) + `/roles:evolve`. Why: flat graduation broke the role-substrate.
- 2026-06-29 — **auditable-unanimity** — panel 1.2.1: require `Steelman:` field on R1-unanimous runs (closes #25). Why: 47-run audit showed 30% R1-unanimous, 0 steelmans logged — guard invisible.
- 2026-06-29 — **marketplace-source** — migrated 12 plugins from broken `{github,path}` to `"./plugins/<name>"` (closes #28). Why: `github` source silently ignores `path`; install was a no-op for every external user.
- 2026-06-27 — **evolve-merge** — 1.1.1 adds *merge same-session clusters* as 4th downward pressure (works pre-14-days when graduation+archive blocked). Why: audit can recommend with no available action.
- 2026-06-27 — **screenshot-tour** — 1.0.0 new plugin: discover → plan → capture → assemble a deck under `presentation/`; driver-agnostic. Why: no product-tour skill existed.
- 2026-06-26 — **evolve-audit** — 1.1.0 adds whole-file size check (25/40 KB), self-report on missing D&L heading, staleness trigger (closes #16). Why: siblings hit size cap; audit stayed silent.
- 2026-06-21 — **research-sweep-learning** — 1.1.3 adds per-run log, thin-agent diagnosis (slice vs agent), demote/retire rule, `## Research sweep` graduation block. Why: closes the only orchestrator without a log.
- 2026-06-11 — **project-goal** — host reusable, self-learning Claude Code skills as a versioned marketplace with Antora docs.
- 2026-06-11 — **marketplace-shape** — one plugin marketplace, per-plugin versioning; details graduated to Conventions/Gotchas. Why: Claude Code versions per plugin.
- 2026-06-12 — **ecosystem-review** — 1.1.0 improvement plan → docs/decisions/2026-06-12-ecosystem-review.md. Why: benchmark before iterating.
- 2026-06-12 — **role-system-shape** — role system first-class across crew/panel/sweep; details graduated to Conventions. Why: unify role vocab.
