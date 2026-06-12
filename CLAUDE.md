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
`parallel-research-sweep` (research).

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
  `nav.adoc` entry.
- **Never push or cut release tags without explicit user confirmation.**

## Gotchas (load-bearing)

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

### Historic (older than 14 days · see git log for the build-up)

- 2026-06-11 — **project-goal** — host reusable, self-learning Claude Code skills as a versioned marketplace with Antora docs.
