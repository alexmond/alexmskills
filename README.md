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
| [`dev-crew`](plugins/dev-crew) | self-learning | 1.0.0 | A self-evolving, role-based delivery relay (architect → dev → qa → deployer), each role a subagent on its own model tier. |
| [`brainstorm-panel`](plugins/brainstorm-panel) | self-learning | 1.0.0 | Assembles a task-fit panel of role-specialized agents, picks a coordination style, and runs a generate-critique-refine loop. |
| [`learn-on-failure`](plugins/learn-on-failure) | self-learning | 1.0.0 | Auto-saves a durable learning to project memory whenever a task takes more than one fix cycle. |
| [`implement-issue`](plugins/implement-issue) | workflow | 1.0.0 | Drives a GitHub issue from branch → implement → verify → PR with a guided workflow. |
| [`maven-quality`](plugins/maven-quality) | workflow | 1.0.0 | Format, static-analysis, coverage, and pre-commit skills for Maven/Java projects (codestyle, precommit, jacoco). |
| [`security-audit`](plugins/security-audit) | workflow | 1.0.0 | Scans a codebase for OWASP-style vulnerabilities (injection, path traversal, unsafe reflection/deserialization, secrets). |
| [`review-agents`](plugins/review-agents) | review | 1.0.0 | Read-only specialist subagents for code review, test running, and dependency/CVE auditing on lighter model tiers. |
| [`parallel-research-sweep`](plugins/parallel-research-sweep) | research | 1.0.0 | Fans out independent research agents across distinct angles, then synthesizes and adversarially verifies. |

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
/plugin install implement-issue@alexmskills
/plugin install maven-quality@alexmskills
/plugin install security-audit@alexmskills
/plugin install review-agents@alexmskills
/plugin install parallel-research-sweep@alexmskills
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
- **`dev-crew`** — *"run the crew on this feature"*. Review the proposed roster, then it relays
  architect → dev → qa → deployer, stopping at hard gates (QA fail, deploy).
- **`brainstorm-panel`** — *"get a team on this and make it better"*. It proposes a panel + a
  coordination style for your sign-off, then runs the loop.
- **`learn-on-failure`** — install it and forget it; it captures a learning whenever a task needed
  more than one attempt.

## Channels

Two marketplace channels ship from this one repo:

- **stable** — `alexmskills` (`.claude-plugin/marketplace.json`): released, versioned plugins.
- **beta** — `alexmskills-beta` ([`beta/`](beta)): unreleased / in-progress plugins. Opt in with a
  `git-subdir` source (see [`beta/README.md`](beta/README.md)), then
  `/plugin install <name>@alexmskills-beta`.

```bash
make new-beta NAME=my-skill     # scaffold an unreleased plugin in the beta channel
make promote PLUGIN=my-skill    # move it into the stable catalog when it's ready
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

## Maintenance

| Command | Purpose |
| --- | --- |
| `make validate` | Validate both channels + every plugin manifest (jq-based, no extra deps). Runs in CI. |
| `make list` | Print the catalog (name, version, description). |
| `make bump PLUGIN=<name> VERSION=<x.y.z>` | Bump a plugin's version in both manifests. |
| `make new-beta NAME=<name>` | Scaffold a new plugin in the beta channel. |
| `make promote PLUGIN=<name>` | Move a beta plugin into the stable catalog. |
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

## License

[MIT](LICENSE) © Alex Mondshain
