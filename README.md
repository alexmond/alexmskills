# alexmskills

[![Validate Marketplace](https://github.com/alexmond/alexmskills/actions/workflows/validate.yml/badge.svg)](https://github.com/alexmond/alexmskills/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-alexmond.org-informational)](https://www.alexmond.org/alexmskills/)

A curated **[Claude Code](https://code.claude.com) plugin marketplace** of reusable, self-improving
skills and agents. Each skill is packaged as an **independently versioned plugin**, so you install and
update exactly what you need.

The emphasis is on **self-learning** tooling — skills that get better at *your* repo over time:
a CLAUDE.md that prunes and graduates its own decisions, a delivery crew that re-tiers its roles from
run history, a brainstorm panel that learns which experts your work needs, and a learn-on-failure hook
that captures every multi-cycle debugging detour.

## Catalog

| Plugin | Category | Version | What it does |
|---|---|---|---|
| [`evolving-claude-md`](plugins/evolving-claude-md) | self-learning | 1.0.0 | Turns CLAUDE.md into a living Decisions & Learnings log that prunes, graduates, and archives itself via three hooks. |
| [`dev-crew`](plugins/dev-crew) | self-learning | 1.1.0 | A self-evolving delivery crew that composes a task-fit roster (like a panel, but to *ship* a target) and runs it as a gated relay with machine-enforced phase gates + an escalation ladder; each role a subagent on its own tier. (architect → dev → qa → deployer is one example lineup.) |
| [`brainstorm-panel`](plugins/brainstorm-panel) | self-learning | 1.1.0 | Assembles a task-fit panel of role-specialized agents (skeptic always seated), picks a coordination style, and runs a generate-critique-refine loop with an evolving seat registry. |
| [`learn-on-failure`](plugins/learn-on-failure) | self-learning | 1.0.0 | Auto-saves a durable learning to project memory whenever a task takes more than one fix cycle. |
| [`roles`](plugins/roles) | self-learning | 1.0.0 | A per-repo repository of evolving roles (.claude/roles/) usable solo via /roles:as, as dev-crew roles, brainstorm-panel seats, and research-sweep coverage roles; ships seed personas + a graduation-audit hook. |
| [`implement-issue`](plugins/implement-issue) | workflow | 1.0.0 | Drives a GitHub issue from branch → implement → verify → PR with a guided workflow. |
| [`maven-quality`](plugins/maven-quality) | workflow | 1.0.0 | Format, static-analysis, coverage, and pre-commit skills for Maven/Java projects (codestyle, precommit, jacoco). |
| [`security-audit`](plugins/security-audit) | workflow | 1.0.0 | Scans a codebase for OWASP-style vulnerabilities (injection, path traversal, unsafe reflection/deserialization, secrets). |
| [`review-agents`](plugins/review-agents) | review | 1.0.0 | Read-only specialist subagents for code review, test running, and dependency/CVE auditing on lighter model tiers. |
| [`research-sweep`](plugins/research-sweep) | research | 1.0.0 | Fans out independent research agents across distinct angles, then synthesizes and adversarially verifies. |

## The Role System

Four of the plugins form **one system**: a shared substrate of **evolving roles** (`.claude/roles/`) and
three **orchestrators** that compose those roles task-fit and learn over time. One persona — say a
`skeptic` or an `architect` — behaves the same whether it's run solo, seated in a crew, on a panel, or in
a sweep, accumulating what it learns along the way.

| Plugin | Role in the system | Verb |
|---|---|---|
| [`roles`](plugins/roles) | the shared substrate — evolving roles + solo invocation (`/roles:as <role>`) | — |
| [`dev-crew`](plugins/dev-crew) | composes a roster and runs it as a **gated delivery relay** | **deliver** |
| [`brainstorm-panel`](plugins/brainstorm-panel) | convenes a **multi-perspective panel** that critiques and converges | **decide** |
| [`research-sweep`](plugins/research-sweep) | fans out **parallel coverage roles** then synthesizes + adversarially verifies | **discover** |

The three orchestrators **chain** — research *discovers* the facts, the panel *decides* what to do, the
crew *delivers* it — and they **share roles** (one `skeptic` is a panel seat, a crew adversarial check,
and a research verifier). Each is fully usable on its own; co-installed, they share one evolving talent
pool. Full model: the
**[Role System architecture](https://www.alexmond.org/alexmskills/role-system/)**.

## Install

Add the marketplace once:

```text
/plugin marketplace add alexmond/alexmskills
```

Then install what you want — copy-paste any of these:

```text
/plugin install evolving-claude-md@alexmskills
/plugin install dev-crew@alexmskills
/plugin install brainstorm-panel@alexmskills
/plugin install learn-on-failure@alexmskills
/plugin install roles@alexmskills
/plugin install implement-issue@alexmskills
/plugin install maven-quality@alexmskills
/plugin install security-audit@alexmskills
/plugin install review-agents@alexmskills
/plugin install research-sweep@alexmskills
```

Or browse interactively with `/plugin` (Discover tab). After a maintainer pushes an update, refresh
with `/plugin marketplace update alexmskills`.

### Try a plugin without installing

```bash
claude --plugin-dir ./plugins/dev-crew
```

## Quick start

- **`evolving-claude-md`** — open a repo and say *"make CLAUDE.md evolve"*. The plugin ships its own
  hooks (audit on session start, lint on every CLAUDE.md edit, re-audit after compaction) — they
  register automatically once the plugin is enabled.
- **`dev-crew`** — *"run the crew on this feature"*. It composes a roster for the task; review it,
  then it relays the roles, stopping at hard gates (QA fail, deploy). architect → dev → qa → deployer
  is the typical code lineup — a data change or a doc gets a different one.
- **`brainstorm-panel`** — *"get a team on this and make it better"*. It proposes a panel + a
  coordination style for your sign-off, then runs the loop.
- **`learn-on-failure`** — install it and forget it; it captures a learning whenever a task needed
  more than one attempt.

## Beta plugins

In-progress / unproven plugins live in the same marketplace as stable ones, distinguished by a
`-beta` suffix in the name (e.g. `prompt-coach-beta`, `tune-repo-beta`). No separate channel, no
extra marketplace to opt into — you install them the same way as any other plugin:

```
/plugin install prompt-coach-beta@alexmskills
```

The suffix is intentional: it makes it obvious at install time and in the enabled-plugins list
that this is a beta plugin. When one earns its stable slot, it graduates — the directory is
renamed, the `-beta` drops from the name and marketplace entry, and the version bumps:

```bash
make graduate PLUGIN=prompt-coach-beta         # renames -> prompt-coach, updates marketplace
make bump     PLUGIN=prompt-coach VERSION=1.0.0
```

## Versioning

Claude Code versions **per plugin**, not per skill. Each plugin carries a semantic `version` in its
`plugin.json` and a matching entry in [`marketplace.json`](.claude-plugin/marketplace.json):

- **Bump a version** to ship an update — users on a pinned version only receive it when the number
  changes (commits alone don't trigger an update).
- Tightly-coupled skills (e.g. `maven-quality`'s codestyle/precommit/jacoco) share one plugin and
  version together; everything else is its own plugin so it can move independently.

```bash
make bump PLUGIN=dev-crew VERSION=1.1.0   # updates plugin.json + marketplace.json together
```

Record every version bump in [`CHANGELOG.md`](CHANGELOG.md).

## Maintenance

| Command | Purpose |
| --- | --- |
| `make validate` | Validate the marketplace + every plugin manifest (jq-based, no extra deps). Runs in CI. |
| `make list` | Print the catalog (name, version, description). |
| `make bump PLUGIN=<name> VERSION=<x.y.z>` | Bump a plugin's version in both manifests. |
| `make graduate PLUGIN=<name>-beta` | Graduate a beta plugin (drop the -beta suffix, bump the marketplace entry). |
| `claude plugin tag --dry-run plugins/<name>` | Validate a plugin's `plugin.json` agrees with its marketplace entry. |
| `claude plugin tag --push plugins/<name>` | Cut a `<name>--v<version>` release tag. |

CI (`.github/workflows/validate.yml`) validates the marketplace on every push and PR.

## Documentation

Full docs are published at **[alexmond.org/alexmskills](https://www.alexmond.org/alexmskills/)**
(Antora component under [`docs/`](docs), aggregated by the
[alexmond.github.io](https://github.com/alexmond/alexmond.github.io) site build).

## Contributing

1. Add a plugin under `plugins/<name>/` with a `.claude-plugin/plugin.json` and a `skills/` and/or
   `agents/` directory.
2. Register it in `.claude-plugin/marketplace.json` (under `plugins`).
3. Run `make validate` — it must pass.
4. Add a doc page under `docs/modules/ROOT/pages/` and link it in `nav.adoc`.

## Provenance & attribution

All plugins in this marketplace are **original work by Alex Mondshain**, MIT-licensed — authorship is
recorded in each plugin's `plugin.json` (`author`) and the repo [LICENSE](LICENSE). One third-party
**inspiration** is credited: the `roles` plugin's persona set was seeded by a public prompt thread from
[@nahidulislam404](https://x.com/nahidulislam404) on X — the wording here is generalized and rewritten,
but that thread sparked the original set.

## License

[MIT](LICENSE) © Alex Mondshain
