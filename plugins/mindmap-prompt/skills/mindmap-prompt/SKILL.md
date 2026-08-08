---
name: mindmap-prompt
description: Think on a canvas, then compile the map into an organized prompt. Drop idea nodes, connect them, and turn the whole map into structured Markdown you can send to Claude — or save it as a JSON Canvas file and pick it up later. Use when the user says "mind map", "map this out", "brain dump", "let me sketch this first", "turn my notes into a prompt", or when a request is big and tangled enough that thinking visually beats writing one long paragraph.
---

# mindmap-prompt

Some ideas don't arrive in order. You drop them, connect them, and *then* the
shape appears. This skill gives you a canvas for that, and a deterministic
compiler that turns the finished map into an organized prompt.

The compile step is plain Python — no LLM, no network. The same map always
produces the same prompt.

## Quick start

```bash
python3 <plugin>/scripts/serve.py --cwd .
```

Opens `http://127.0.0.1:8770/`. A fresh map starts with one root node, already
focused — type over it, then branch with `Tab`, `Enter` or the `+` handle. To edit any
node later, select it and just start typing.

| Key | Does |
|---|---|
| **just type** | **edit the selected node** — typing replaces its text |
| click, click again | edit a node (or double-click) |
| `+` on a node | add an idea on that side (a fresh map starts with one root to type over) |
| `Enter` | commit + new sibling (`Shift+Enter` = new line inside a node) |
| `Tab` | commit + new child |
| `Ctrl/Cmd`+arrow | new connected node in that direction |
| drag `+` to another node | connect two nodes (a cross-link) |
| `✦` on a node, or `Ctrl/Cmd+.` | expand it with `claude -p` (see below) |
| `1` `2` `3` `4` | goal · feature · idea · constraint |
| `Ctrl/Cmd+S` | save the map |
| `Ctrl/Cmd+Enter` | validate + compile |

Maps are saved to `.claude/mindmap/<name>.canvas` in the current repo.

## ✦ Expanding an idea

Select a node, press `✦` (or `Ctrl/Cmd+.`), and the node is handed to `claude -p`
running **in this repo** — so the project's `CLAUDE.md` and vocabulary shape the
answer. Quick actions: *Expand into ideas*, *Break into steps*, *Name constraints*
(all add children), *Sharpen wording*, *Add done-criteria* (both rewrite the node).
Free-text works too.

- **The map is the context** — the goal, ancestor chain, siblings and existing
  children travel with the request. An idea expanded without its goal is generic.
- **Nothing is applied until the user presses the apply button.** Results sit in
  the panel; closing it leaves the map untouched.
- **Every tool is denied** (`--allowed-tools ""`), so the subprocess reads the
  project and writes prose — it cannot touch a file.

The control is hidden when the `claude` CLI isn't on `PATH`. `serve.py --no-ai`
disables it; `--ai-model <name>` picks a different model.

## The four kinds

v1 keeps the vocabulary small on purpose.

| Kind | Use it for | Where it lands in the prompt |
|---|---|---|
| **goal** | the task, and what "done" means | the `#` title + opening paragraph |
| **feature** | a deliverable or major section | a `##` section |
| **idea** | detail hanging off something else | a nested heading |
| **constraint** | what must *not* change | a `## Constraints` bullet |

Exactly one goal per map — it's the entry point the compiler starts from.

Kinds are stored as a leading tag in the node's text (`#goal Ship dark mode`),
so a `.canvas` file round-trips through Obsidian Canvas unchanged.

## How a map becomes a prompt

1. **Order comes from your layout.** Sibling nodes compile top-to-bottom, then
   left-to-right. You already arrange ideas spatially while thinking — that
   arrangement *is* the document order, so there's no re-ordering step.
2. **Structure comes from a spanning tree.** Every node is owned by its
   shortest-path parent from the goal, so anything wired straight to the goal
   stays a top-level section.
3. **Cross-links become references.** A second edge into an already-placed node
   compiles to `→ see "That node"` instead of repeating it. Cross-links and
   cycles are fine — nothing is duplicated and nothing is lost.
4. **Edge labels survive.** Label an edge `depends on` and it shows up on the
   target's heading.

## Validation runs first

Compile always validates. Errors block; warnings don't.

- **Errors** — no goal, more than one goal, an empty node, a goal with no connections.
- **Warnings** — nodes not connected to the goal; a goal that never says what "done" is.
- **Info** — no constraints yet.

Orphan nodes are never silently dropped. Either connect them, or compile with
`--include-orphans` and they land under `## Unsorted notes`.

## Headless use

The canvas is optional. The compiler is a normal CLI, so a map can be compiled
in a script, in CI, or straight from a chat turn:

```bash
python3 <plugin>/scripts/mindmap.py validate .claude/mindmap/feature.canvas
python3 <plugin>/scripts/mindmap.py compile  .claude/mindmap/feature.canvas -o prompt.md
python3 <plugin>/scripts/mindmap.py compile  .claude/mindmap/feature.canvas --include-orphans
```

`validate` exits non-zero when the map has errors, so it works as a gate.

## What to do when the user asks

1. **"map this out" / "let me sketch first"** → start the server with `--cwd` set to
   the repo, tell them the URL, and stop. Don't narrate the keys — the `?` button has them.
2. **"compile my map" / "turn that into a prompt"** → find the map under
   `.claude/mindmap/`, run `mindmap.py compile`, and **use the output as the actual
   prompt** — read it, then do the work it describes. Don't just print it back.
3. **"what maps do I have?"** → list `.claude/mindmap/*.canvas`.
4. **A map exists and the user asks for related work** → check whether it already
   covers the request before asking them to re-explain it.

If the compile reports warnings, surface them in one line — especially orphans,
because that's content the user wrote that won't reach the prompt.

## Notes

- **Capture and compile are offline.** The page makes no external requests and the
  server binds `127.0.0.1` only. The one exception is the `✦` expander: it shells
  out to `claude -p`, which reaches Anthropic like any other Claude Code turn and
  sends the node plus its surrounding map. Nothing is sent unless you press it, and
  `serve.py --no-ai` removes the control entirely.
- **State lives in the consuming repo** (`.claude/mindmap/`), never in the plugin
  directory — an installed plugin is a read-only cache.
- **`.canvas` is JSON Canvas 1.0** — plain JSON, diffs cleanly in git, and opens in
  Obsidian.
- Deliberately *not* a chain builder or an agent canvas. It compiles one prompt.
