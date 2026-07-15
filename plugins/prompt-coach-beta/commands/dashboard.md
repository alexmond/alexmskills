---
description: Launch the local prompt-coach web dashboard (stats, mastery, live config editor)
---

# `/prompt-coach-beta:dashboard`

Start the coach's **lightweight local web dashboard** — a zero-dependency
(Python stdlib only) server bound to `127.0.0.1` that shows stats, mastery by
tier with reference-URL links, and a **live config editor** (writes go through
the same schema validation the CLI uses).

## What to do

1. Locate the plugin's `scripts/serve.py` (installed cache path
   `~/.claude/plugins/cache/alexmskills/prompt-coach-beta/*/scripts/serve.py`,
   else the dev checkout).
2. Launch it **in the background** so this session stays interactive, pointed at
   the current repo (for repo-scoped config):

   ```bash
   python3 <plugin>/scripts/serve.py --cwd "$PWD" --port 8765
   ```

   If port 8765 is taken, pass `--port 0` to get a free one; read the printed
   `http://127.0.0.1:<port>/` line and give the user that URL.
3. Print the URL and tell the user to open it. Note that it's **local only**
   (127.0.0.1) and edits the same `~/.claude/prompt-coach/` + repo
   `.claude/prompt-coach/` state the hook and CLI use.
4. To stop it later: kill the background process (or Ctrl-C if foreground).

## What the dashboard shows

- **Stats** — prompts analyzed, mastered / inactive / in-progress / dormant counts.
- **Mastery** — every rule grouped by tier (L1–L6) with a status badge,
  `demos/min` progress, `fires`, its guidance, and clickable **reference URLs**
  (Anthropic guide + every cited source). A per-rule **reset** button.
- **Config** — every schema key with its description, current value + scope, and
  a type-aware control (checkbox / number / select / text). Editing **saves
  live** to the chosen scope (global or repo, selectable top-right). `↺` resets
  a key to default.
- **Options** — reset-all-mastery, refresh, open the Anthropic guide.

## Data-only alternative

For the raw consolidated JSON without the server (scripting, piping):

```bash
python3 <plugin>/scripts/config.py --cwd "$PWD" dashboard
```

## What NOT to do

- Do NOT bind to `0.0.0.0` or expose it off-host — it's a local tool with no
  auth by design.
- Do NOT reimplement reads/writes — `serve.py` reuses `config.py`'s
  `build_dashboard` / `api_set` / `api_action`, so the schema validation and
  scope rules stay identical to the CLI.
