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

- 2026-06-11 — **marketplace** — repo restructured as a plugin marketplace; each skill is its own versioned plugin under `plugins/`. Why: Claude Code versioning is per-plugin, not per-skill.
- 2026-06-11 — **provenance** — skills curated + generalized from venice-vr, the dev-crew zip, and jhelm / yj-schema-validator / spring-boot-config. Why: real, battle-used sources beat greenfield.
- 2026-06-11 — **versioning** — `make bump` edits plugin.json + marketplace.json together; `claude plugin tag` cuts `<name>--v<version>` tags. Why: stop the two manifests' versions from drifting.
- 2026-06-11 — **docs** — Antora component at `docs/` (version `~`); built + deployed by alexmond.github.io to alexmond.org/alexmskills. Why: matches every other alexmond repo.
- 2026-06-11 — **ci** — `make validate` (pure jq/bash) runs in GitHub Actions on push/PR; no claude CLI needed. Why: reliable validation with zero external deps.
- 2026-06-11 — **dogfood** — this repo runs evolving-claude-md on its own CLAUDE.md via `.claude/skills/evolving-claude-md` + settings.json hooks. Why: the marketplace should eat its own dog food.
- 2026-06-11 — **beta-channel** — second marketplace at `beta/` (alexmskills-beta) for unreleased plugins; `make new-beta`/`make promote` move them. Why: ship experiments without polluting stable.
- 2026-06-12 — **ecosystem-review** — field survey + 1.1.0 improvement plan for dev-crew/brainstorm-panel/senior-prompts. Why: benchmark before iterating. See → docs/decisions/2026-06-12-ecosystem-review.md.
- 2026-06-12 — **role-system** — roles first-class & evolving; crew/panel registries at `.claude/roles/{crew,panel}.md`; beta `roles` plugin adds shared core + `/roles:as`; senior-prompts absorbed.
- 2026-06-12 — **escalation** — dev-crew 1.1.0 adds BLOCKED handoff + phase-gate hook + diagnosis ladder (retry → re-tier vs re-role → re-plan → user). Why: stumbling roles had no defined path.
- 2026-06-12 — **research-discover** — research-sweep 1.1.0 joins the role system as the 'discover' orchestrator: registry `.claude/roles/research.md`, evolving coverage roles, learning. Why: parity with crew/panel.
- 2026-06-12 — **naming** — convention: orchestrators `<scope>-<team-noun>` (crew/panel/sweep); roles named as personas (noun) not tasks; coverage roles `<dimension>-scout`. Why: catalog looked random.
- 2026-06-12 — **renames** — `parallel-research-sweep`→`research-sweep`; role personas → crew-aligned nouns (architect/debugger/optimizer/reviewer/refactorer/builder). Why: unify role vocab.
- 2026-06-12 — **attribution** — roles personas credit @nahidulislam404's prompt thread as inspiration; all plugins are Alex's own original work (MIT, per plugin.json author). Why: public-repo provenance.
- 2026-06-21 — **research-sweep-learning** — 1.1.3 adds per-run log, thin-agent diagnosis (slice vs agent), demote/retire rule, `## Research sweep` graduation block. Why: closes the only orchestrator without a log.
- 2026-06-26 — **evolve-audit** — 1.1.0 adds whole-file size check (25/40 KB), self-report on missing D&L heading, staleness trigger (closes #16). Why: siblings hit size cap; audit stayed silent.
- 2026-06-27 — **evolve-merge** — 1.1.1 adds *merge same-session clusters* as 4th downward pressure (works pre-14-days when graduation+archive blocked). Why: audit can recommend with no available action.
- 2026-06-27 — **screenshot-tour** — 1.0.0 new plugin: discover → plan → capture → assemble a deck under `presentation/`. Driver-agnostic (Selenium/Selenide/Playwright/VHS/Freeze). Why: marketplace had single-shot screenshot skills, no product tour.
- 2026-06-29 — **graduation-layers** — panel/crew 1.2.0 + roles 1.1.0: 3-layer split (registry / shared core / CLAUDE.md repo facts) + `/roles:evolve`. Why: flat graduation broke the role-substrate.
- 2026-06-29 — **auditable-unanimity** — panel 1.2.1: require `Steelman:` field on R1-unanimous runs (closes #25). Why: 47-run audit showed 30% R1-unanimous, 0 steelmans logged — guard invisible.
- 2026-06-29 — **marketplace-source** — migrated 12 plugins from broken `{github,path}` to `"./plugins/<name>"` (closes #28). Why: `github` source silently ignores `path`; install was a no-op for every external user.
- 2026-07-01 — **prompt-coach-beta** — new 0.1.0 beta: UserPromptSubmit hook nudges toward better prompts (11 rules, 3 tiers); global mastery + per-repo overrides; configurable mode. Why: prompt quality drives downstream.
- 2026-07-01 — **prompt-coach-advanced** — 0.2.0: +13 rules across L3 classical (CoT, few-shot, rubric, uncertainty), L4 goals/loops, L5 tool-native (plan mode, TaskCreate, agents, roles, panel, Workflow). Why: v0.1 missed advanced concepts.
- 2026-07-01 — **prompt-coach-praise-skills** — 0.4.0: +21 positives (sparing praise per Kohn/Dweck/Fogg) + mastery/first-after-fire + L6 skill-awareness (rule of three). Why: coach should praise + know its ecosystem.
- 2026-07-02 — **prompt-coach-typo-tolerance** — 0.5.0: Levenshtein pre-pass on ~90 trigger words + adaptive tolerance + fallback-count stats. Why: dyslexic-friendly; rising fallback rate signals catalog gaps.
- 2026-07-02 — **beta-source-clone-root** — bare-string plugin sources resolve from CLONE ROOT, not the marketplace.json parent. Beta plugins need `./beta/plugins/<n>`. Why: subdir install failed silently.
- 2026-07-02 — **retire-beta-channel** — dropped beta channel; in-progress plugins now live in stable with `-beta` suffix (prompt-coach-beta, tune-repo-beta). Why: subdir/url/git-subdir workarounds kept multiplying.
- 2026-07-02 — **prompt-coach-conversational** — 0.6.0: skips analysis on approvals/multi-choice/continuations; praise_ratio default 10→3 for trial visibility. Why: coach misfired on "sure"/"1 and 2".

### Historic (older than 14 days · see git log for the build-up)

- 2026-06-11 — **project-goal** — host reusable, self-learning Claude Code skills as a versioned marketplace with Antora docs.
