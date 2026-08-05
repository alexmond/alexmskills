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
Both completed but the final *synthesis* step was cut off by a session/token limit, so
below is a hand synthesis of the verified claims. **Resume pointers at the bottom.**

- Prior-art / build-vs-adopt: run `wf_49d7e3d4-a76`
- Design patterns: run `wf_9c1a5e58-4e3`

## Verdict: BUILD (the niche is real)

No existing tool is an **offline, dependency-free, Claude-Code-native map → *one
organized prompt* with save-for-later**. Everything close is either Obsidian-locked,
cloud/commercial, or a runtime-chain builder (not an idea-map compiler).

### Closest genuine matches (same core idea: user-built map → prompt)
- **obsidian-llm-plugin (LLeen)** — reads selected Obsidian Canvas nodes, walks graph
  topology, RENDERS a structured Markdown prompt (incl. a Graph TD/Mermaid section).
  *Genuinely map→prompt* — the closest true prior art. But: Obsidian-bound, calls an
  OpenAI-compatible API, not standalone. **Emulate its compile logic**, don't adopt.
- **ContextMinds** (contextminds.com) — "the map becomes a living prompt: generate a
  summary/outline/draft in one click." Genuine, but **commercial cloud SaaS (Prague),
  not open/offline** — cannot fork/vendor. (verified 3-0 commercial; 2-1 same-idea)
- **Nodus MD** — visual flow editor, connected nodes → clean Markdown. Same idea, but
  commercial/cloud, product-flow niche.
- **prompt-canvas (JohnnyJi1)** — local-first single-page app, no backend, LocalStorage,
  **MIT, vanilla JS**. BUT it manages connected *prompt* nodes (chaining), not
  idea-map → *one* organized prompt. Adjacent. (Worth reading its single-file structure
  as a build reference — MIT so vendorable.)
- **kepano/obsidian-skills → json-canvas skill** — official Obsidian agent skill to
  read/write JSON Canvas; oriented to *authoring* the canvas, not compiling map→prompt.

### Not matches — runtime-chain / agent builders (verified adjacent, NOT the idea)
ChainForge (prompt eval), Rivet (agent builder), Langflow (runtime flows), LLM Canvas
(conversation viz), pipelineLLM (runtime pipeline). All confirmed *adjacent*, not
map→organized-prompt.

### Opposite direction (fail the map→prompt test — do NOT count as prior art)
Mapify/ChatMind/XMind AI (text→map), markmap (Markdown→mindmap), claude-canvas
(text→canvas), NotebookLM→Canvas plugin. All generate maps *from* text — the reverse.

### Differentiated niche for our skill
Standalone · offline · zero-dep · MIT · **not Obsidian-locked, not cloud, not a
runtime-chain builder** · output flows straight into the Claude Code prompt · saves the
map to the repo (`.claude/`) for future work.

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

- Both workflows' **synthesis** step failed on the session limit; several verify votes
  errored (counted `unverified`, not refuted). The confirmed claims above are solid;
  the `unverified` tool details (prompt-canvas MIT/vanilla, obsidian-canvas-llm GPL-3.0,
  Canvas LLM, etc.) are **plausible but not adversarially confirmed** — re-verify before
  relying on any specific license/offline claim.
- Design-research angle 5 (compilation) and accessibility got the least verification.

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
