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

Add the beta channel alongside the stable one. The beta marketplace is fetched by direct URL
(no repo clone needed), and each plugin inside it declares its own `git-subdir` source so only
the plugin's subtree is materialized on install. In `.claude/settings.json` (project) or
`~/.claude/settings.json` (global):

```json
{
  "extraKnownMarketplaces": {
    "alexmskills-beta": {
      "source": {
        "source": "url",
        "url": "https://raw.githubusercontent.com/alexmond/alexmskills/main/beta/.claude-plugin/marketplace.json"
      }
    }
  }
}
```

Then `/plugin install <name>@alexmskills-beta`. To evaluate locally without installing:

```bash
claude --plugin-dir ./beta/plugins/<name>
```

### Why this shape

The `url` source is the *simplest* way to add a marketplace — the CLI fetches one file, no repo
clone, no `sparsePaths` gotcha, no dual `.claude-plugin/marketplace.json` at repo root vs subdir
confusion. The plugins inside the marketplace declare `git-subdir` sources per plugin:

```json
"source": {
  "source": "git-subdir",
  "url": "alexmond/alexmskills",
  "path": "beta/plugins/prompt-coach"
}
```

`git-subdir` sparsely clones only the plugin's subtree (via `--filter=tree:0`), keeping install
bandwidth minimal. The stable channel keeps using bare-string sources (`"./plugins/<name>"`)
because its marketplace.json lives at repo root — that convention still works for the root case
and is one line per plugin, so no reason to change it.

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
