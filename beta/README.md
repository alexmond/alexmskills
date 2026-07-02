# alexmskills — beta channel

This directory is a **separate marketplace** (`alexmskills-beta`) for plugins that are **not yet
released** to the stable [`alexmskills`](../README.md) catalog: new skills, experiments, and
in-progress work. Expect breaking changes and rough edges.

## Layout

```
beta/
├── .claude-plugin/marketplace.json   # the beta catalog (name: alexmskills-beta)
└── plugins/<name>/                   # unreleased plugins, same structure as stable plugins/
```

## Opt in to beta

Add the beta channel alongside the stable one. Beta lives at
`beta/.claude-plugin/marketplace.json`, so it's added as a `github` source with the marketplace
`path` pointing inside the repo. In `.claude/settings.json` (project) or `~/.claude/settings.json`
(global):

```json
{
  "extraKnownMarketplaces": {
    "alexmskills-beta": {
      "source": {
        "source": "github",
        "repo": "alexmond/alexmskills",
        "path": "beta/.claude-plugin/marketplace.json",
        "sparsePaths": ["beta"]
      }
    }
  }
}
```

`sparsePaths: ["beta"]` keeps the clone lean — only the `beta/` subtree is checked out. Note:
`git-subdir` is only valid as a **plugin** source, not a marketplace source — the marketplace
source schema uses `github` + `path` for the marketplace.json location.

Then `/plugin install <name>@alexmskills-beta`. To evaluate locally without installing:

```bash
claude --plugin-dir ./beta/plugins/<name>
```

## Workflow

| Action | Command |
|---|---|
| Scaffold a new beta plugin | `make new-beta NAME=<name>` |
| Validate both channels | `make validate` |
| Promote a plugin to stable | `make promote PLUGIN=<name>` |

**Promotion** moves `beta/plugins/<name>` → `plugins/<name>`, removes the entry from this beta catalog,
and adds it to the stable `.claude-plugin/marketplace.json`. After promoting, set a real release
version with `make bump` and add a docs page.
