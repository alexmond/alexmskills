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

Add the beta channel alongside the stable one. Beta is a git **subdirectory** of the repo, so it's
added as a `git-subdir` source. In `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "alexmskills-beta": {
      "source": { "source": "git-subdir", "url": "alexmond/alexmskills", "path": "beta" }
    }
  }
}
```

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
