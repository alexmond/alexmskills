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

### Historic (older than 14 days · see git log for the build-up)

- 2026-06-11 — **project-goal** — host reusable, self-learning Claude Code skills as a versioned marketplace with Antora docs.
- 2026-06-11 — **marketplace-shape** — one plugin marketplace, per-plugin versioning; details graduated to Conventions/Gotchas. Why: Claude Code versions per plugin.
- 2026-06-12 — **ecosystem-review** — 1.1.0 improvement plan → docs/decisions/2026-06-12-ecosystem-review.md. Why: benchmark before iterating.
- 2026-06-12 — **role-system-shape** — role system first-class across crew/panel/sweep; details graduated to Conventions. Why: unify role vocab.
