# New skill: mind-map → prompt — research + build-vs-adopt (2026-08-05)

**Status:** research complete, pre-design. No code yet. Working name: `mindmap-prompt`
(alternatives: `map-to-prompt`, `idea-map`, `prompt-map`). Lives in `alexmskills`
(generic/portable, no lab leak).

**Concept:** a self-contained JS canvas where the user drops idea nodes and connects
them, then compiles the map into an *organized prompt / Markdown* — with a validation
pass, and two exits: send straight to a prompt, or save the map for future work.
Precedent for a skill shipping a local JS page: prompt-coach's dashboard, screenshot-tour.

## How this was researched

Two background `deep-research` workflows (fan-out search → fetch → adversarial verify).

- **Prior-art / build-vs-adopt: run `wf_49d7e3d4-a76` — COMPLETE (resumed 2026-08-07).**
  105/105 agents, 0 errors. 6 angles → 22 sources → 94 claims extracted → 25 verified →
  **25 confirmed, 0 refuted, 0 unverified** → 6 synthesized findings. High confidence.
- Design patterns: run `wf_9c1a5e58-4e3` — **synthesis still incomplete.** First pass had
  its synthesis cut by the token limit; the resume then failed on quota (30/105, all
  verify panels errored — the harness itself flagged this as "an infrastructure failure,
  not a research finding"). The design claims below are therefore *extracted but not
  adversarially confirmed*. They are low-risk descriptive facts about public specs
  (JSON Canvas shape, keybindings, licenses) — treat as directional, verify before
  relying on any exact license claim.

## Verdict: BUILD (the niche is real) — CONFIRMED, high confidence

No existing tool is an **offline, dependency-free, Claude-Code-native map → *one
organized prompt* with save-for-later**. Everything close is either Obsidian-locked,
cloud/commercial, or a runtime-chain builder (not an idea-map compiler). **Exactly two**
tools do the target direction at all, and neither is adoptable.

### The only two genuine map → organized-prompt tools (both unadoptable)
- **ContextMinds** (contextminds.com) — "the map becomes a living prompt: generate a
  summary/outline/draft in one click." A real user-built-map→prompt flow. **But:**
  Prague-based proprietary SaaS (~$8–84/mo), no repo, no license → **cannot be forked or
  vendored.**
- **obsidian-llm-plugin (LLeen)** — README describes `Canvas selection → ContextPacket →
  Markdown prompt → LLM request`; walks graph topology and renders a structured prompt
  (incl. a Graph TD/Mermaid section). The **closest true prior art**. **But:** bound to
  the Obsidian Plugin API (Node/TS), requires an external LLM API key via `requestUrl`,
  and is aspirational WIP (still carries community-plugin boilerplate, not in the plugin
  directory). **Emulate its compile logic; do not adopt it.**

### Closest reusable CODE (not the same idea)
- **prompt-canvas (JohnnyJi1)** — MIT (LICENSE: "Copyright (c) 2026 JohnnyJi1"), fully
  offline (`open index.html`, LocalStorage), **no backend / no build step / vanilla JS**
  → legally vendorable. **But** it organizes, versions and reuses *connected prompt
  nodes* (with `{{variable}}` templating), not idea-map → one organized prompt — and the
  repo is **2 commits, 0 stars**. Read it for single-file structure; don't build on it.

### Not matches — runtime chain / agent / chat canvases (all verified 3-0 adjacent)
- **Langflow** — "create and serve flows … functional representations of application
  workflows"; output is a served app/API, not a prompt.
- **Rivet** — "visual programming environment for building AI agents"; graphs are YAML
  runtime artifacts run inside an app. No compile-to-prompt.
- **ChainForge** — "battle-testing prompts to LLMs"; combinatorial eval/comparison.
- **pipelineLLM** — runtime execution primitives via a Flask backend.
- **llm-canvas** — conversation *debugger*: nodes are chat messages with branching.
- **Canvas LLM (Obsidian)** — branching LLM conversations. Its own plugin page states it
  **"doesn't convert existing mind-maps into prompts"** — users construct the flow node
  by node. (GPL-3.0 anyway → copyleft-encumbered for an MIT skill.)

### Opposite direction (fail the map→prompt test — NOT prior art)
Taskade ("generate AI-powered mind maps"), MyMap.AI ("turns conversations into mind
maps"), Mapify/ChatMind/XMind AI, markmap (Markdown→mindmap), claude-canvas (text→canvas),
NotebookLM→Canvas plugin. All generate maps *from* text — the reverse. This confirms the
adversarial caveat: **"AI mind map" almost always means map-FROM-text.**

### The Claude-Code-native niche is verified OPEN
- **kepano/obsidian-skills → `json-canvas`** — *creates and edits* JSON Canvas files
  (nodes, edges, groups); it **authors** the graph, it does not compile it into a prompt.
  None of its 5 skills convert a map/Canvas/Mermaid into an LLM prompt.
  (Correction to an earlier note: this is **not** an official Anthropic/Obsidian repo —
  the research flagged that attribution as an overreach.)
- **outl** — local-first Markdown outliner exposing notes to Claude/Cursor/Zed via MCP;
  that's *LLM-reads-your-notes*, not visual-artifact→prompt.

### Differentiated niche for our skill
Standalone · offline · zero-dep · MIT · **not Obsidian-locked, not cloud, not a
runtime-chain builder** · output flows straight into the Claude Code prompt · saves the
map to the repo (`.claude/`) for future work. **No existing tool fills all four
constraints at once.**

## Design recommendations (from the design-patterns research)

**Interaction model — hybrid freeform graph + keyboard capture.** The user "connects"
ideas → it's a general graph, not a strict tree. Emulate:
- **Kinopio** — *tap anywhere and start typing* to create a card (toolbar-free), and
  **drag from a per-card connector handle** ("patch cable") to link. Frictionless capture.
  (verified 3-0)
- **Excalidraw** — single-key shortcuts + **Cmd/Ctrl+Arrow creates a connected node in a
  direction, repeatable** → grows a connected graph fast without leaving the keyboard.
  (verified 3-0)
- **MindMup** — keyboard-first; note Tab/Enter child-vs-sibling roles are
  *layout-dependent* (horizontal: Enter=sibling/Tab=child; vertical: swapped). (verified 3-0)

**Save format — JSON Canvas (.canvas).** MIT open format (Obsidian), top level = `nodes`
+ `edges` arrays (general graph, optional) → matches a freeform node-graph, human-diffable,
git-friendly, gives data ownership, and buys **Obsidian Canvas interop for free**.
Best "future work" save format. (verified 3-0, two sources)

**Rendering tech — hand-rolled SVG + DOM, zero-dep (recommended default).** For a small
dependency-free tool, hand-rolled SVG (edges) + HTML/DOM (nodes) is viable and preferable
— same posture as prompt-coach's dashboard. If a lib is ever wanted: **Cytoscape.js**
(MIT, standalone UMD/ESM, fully offline, no CDN) or **jsMind** (BSD, canvas+SVG, pure JS,
but tree-oriented). Both vendorable into one file. (verified 3-0)

**Map → prompt compilation.** root node = goal / definition-of-done; branches = sections;
sibling order = document order; edge labels/types → prose connectors. Linearize a
non-tree graph by DFS from the root with visited-tracking (handle cross-links/cycles by
referencing, not duplicating). Intersect with good prompt structure: task · context ·
constraints · output format (borrow the coach's own rule vocabulary). Optionally emit a
Mermaid `graph TD` block for the structural view (as obsidian-llm-plugin does).

**Accessibility / dyslexia-friendly:** plain node labels, generous spacing, high-contrast
theme-aware colors, keyboard-first (don't require the mouse). (design-research angle;
some verify votes cut short by the limit — treat as directional.)

## Proposed shape (for the eventual design)

1. `serve.py` (stdlib, 127.0.0.1) serves a self-contained `mindmap.html` (like the coach
   dashboard) — OR ship a static single-file HTML opened directly.
2. Canvas: tap-to-add, drag-to-connect, node types (goal / feature / idea / question /
   constraint), optional edge labels.
3. Save/load `.canvas` (JSON Canvas) under `.claude/mindmap/` in the consuming repo.
4. "Compile" button → validation pass (has a goal/root? orphans? empty nodes?) → organized
   prompt/Markdown → copy to clipboard OR write to a file OR hand to Claude Code.
5. SKILL.md drives the flow; the compile logic can live in Python (map JSON → prompt).

## Caveats on the research

- **Prior art: resolved.** The 2026-08-07 resume completed clean (25/25 confirmed, 0
  refuted, 0 unverified). The tool details that were previously unverified —
  prompt-canvas MIT/vanilla/offline, Canvas LLM GPL-3.0 and its explicit
  "doesn't convert mind-maps into prompts", obsidian-llm-plugin's WIP status — are now
  **confirmed**. One earlier claim was **corrected**: kepano/obsidian-skills is not an
  official Anthropic/Obsidian repo.
- **Design research: still unconfirmed.** Its synthesis never ran (token limit, then
  quota). Claims are extracted-but-unverified; they're descriptive facts about public
  specs, so risk is low, but **check the JSON Canvas spec and any license directly**
  before committing to them in code. Angle 5 (compilation) and accessibility got the
  least coverage — the compile algorithm below is therefore *designed*, not sourced.
- Re-running the design synthesis is optional; it would harden citations, not change the
  build decision.

## Resume pointers (for a future session after token reset — 6pm America/Toronto)

Raw outputs (scratchpad — may be swept):
- `/tmp/claude-1000/-home-alexm-IdeaProjects-alexmskills/341e464c-49cc-4898-bb8d-bba936466699/tasks/wf1setdds.output` (prior-art)
- `/tmp/claude-1000/-home-alexm-IdeaProjects-alexmskills/341e464c-49cc-4898-bb8d-bba936466699/tasks/wea0gn952.output` (design)

Durable transcripts (per-agent results, one `{"type":"result"}` per line):
- `~/.claude/projects/-home-alexm-IdeaProjects-alexmskills/9f825ec4-2263-4e7a-9678-e85be2b951b2/subagents/workflows/wf_49d7e3d4-a76/journal.jsonl`
- `~/.claude/projects/-home-alexm-IdeaProjects-alexmskills/9f825ec4-2263-4e7a-9678-e85be2b951b2/subagents/workflows/wf_9c1a5e58-4e3/journal.jsonl`

Workflow scripts (re-runnable; resumeFromRunId is same-session only, so a new session
re-runs fresh via name+args or scriptPath):
- `~/.claude/projects/-home-alexm-IdeaProjects-alexmskills/9f825ec4-2263-4e7a-9678-e85be2b951b2/workflows/scripts/deep-research-wf_49d7e3d4-a76.js`
- `~/.claude/projects/-home-alexm-IdeaProjects-alexmskills/9f825ec4-2263-4e7a-9678-e85be2b951b2/workflows/scripts/deep-research-wf_9c1a5e58-4e3.js`

Next step: turn the "Proposed shape" into a real design (interaction spec + JSON-Canvas
schema + compile algorithm), then build the single-file canvas + serve.py + SKILL.md.
