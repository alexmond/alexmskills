# mind-map → prompt skill — design (2026-08-07)

**Status:** design. No code yet. Follows
[`2026-08-05-mindmap-prompt-skill-research.md`](2026-08-05-mindmap-prompt-skill-research.md)
(verdict: BUILD, confirmed high-confidence).

Working name: **`mindmap-prompt`**. Plugin in `alexmskills`, MIT, project-agnostic.

## 1. Product shape

One page, three verbs: **capture → validate → compile**.

```
  drop ideas, connect them          check it's prompt-ready         two exits
  ┌────────────────────┐            ┌──────────────────┐            ┌──────────────┐
  │  canvas (SVG+DOM)  │ ─────────► │  validation pass │ ─────────► │ → prompt     │
  │  nodes + edges     │            │  errors / warns  │            │ → save .canvas│
  └────────────────────┘            └──────────────────┘            └──────────────┘
```

- **Compile now** → organized Markdown prompt, copied to clipboard *and* handed to Claude Code.
- **Save for later** → `.canvas` file in the repo, reopened and reworked any time.

Non-goals (explicit): not a runtime chain builder, not an agent canvas, no LLM call from
the page, no cloud, no accounts. The page never makes a network request.

## 2. Interaction model — hybrid freeform graph, keyboard-first

The user connects ideas arbitrarily → the data model is a **general directed graph**, not
a tree. But compilation needs an *order*, so the design adds one constraint: **exactly one
`goal` node** acts as the entry point. Everything else is free.

Borrowed, per the research:

| Source | Borrow |
|---|---|
| **Kinopio** | Click empty canvas → **type immediately**. No tool palette, no mode. Drag from a per-node **connector handle** to link ("patch cable"). |
| **Excalidraw** | **`Ctrl/Cmd+Arrow`** creates a *connected* node in that direction and focuses it — repeat to grow a branch without touching the mouse. |
| **MindMup / MindMeister** | `Tab` = child, `Enter` = sibling while a node is selected. (Research note: in real mind-mappers these swap by layout orientation — we **fix** them to avoid the confusion.) |

Core bindings (deliberately small):

```
click empty canvas   new node, editing
double-click node    edit text
Tab                  child of selection (connected)
Enter                sibling of selection (connected to same parent)
Ctrl/Cmd+Arrow       connected node in a direction
drag connector       connect two nodes
Esc                  commit text / deselect
Del                  delete selection
1..7                 set node kind
Ctrl/Cmd+S           save .canvas
Ctrl/Cmd+Enter       validate + compile
```

**Spatial order is meaningful.** Sibling order = canvas reading order (`y`, then `x`).
This is the key trick: the user already arranges ideas spatially while thinking, so
position supplies the document order for free — no manual re-ordering step.

**Accessibility / dyslexia-friendly** (house style, per CLAUDE.md):
system UI font at comfortable size, generous line-height and node padding, high-contrast
theme-aware palette (light + dark via `prefers-color-scheme`), **kind conveyed by label
text and shape, never by color alone**, full keyboard operation, no timed interactions,
plain-word labels ("Goal", "Must not", "Open question" — not jargon).

## 3. Data model — JSON Canvas, with kinds encoded compatibly

Save format is **JSON Canvas** (`.canvas`) — verified directly against the 1.0 spec:
top level is two optional arrays `nodes` and `edges`; every node has
`id, type, x, y, width, height` (+ optional `color`); `type` ∈ `text | file | link | group`;
text nodes carry `text` (Markdown). Edges have `id, fromNode, toNode` (+ optional
`fromSide, toSide, fromEnd, toEnd, color, label`).

Why: plain JSON, human-diffable, git-friendly, re-importable, and **free Obsidian Canvas
interop** — open the same file in Obsidian and it just works.
*(Caveat: the spec page itself states no license; the format is published openly by
Obsidian and widely described as MIT. Confirm on the spec repo before asserting MIT in
user-facing docs.)*

**The catch:** JSON Canvas has **no custom node type**, so our kinds need an encoding.
Decision — **encode the kind in the node's Markdown text as a leading tag**, and mirror it
in `color` for visual scanning:

```jsonc
{
  "id": "n1", "type": "text", "x": 0, "y": 0, "width": 300, "height": 90,
  "color": "4",
  "text": "#goal Ship the mind-map prompt skill\n\nDone = ..."
}
```

Rationale: survives a round-trip through Obsidian (it's just Markdown + a standard color),
needs no non-standard keys, and stays human-readable in a diff. Colors are decoration; the
tag is the source of truth. Unknown/absent tag → `idea` (the neutral default).

**Kinds** (7, keys `1..7`):

| Kind | Tag | Role in the compiled prompt |
|---|---|---|
| Goal | `#goal` | The task + definition of done. Exactly one. Entry point. |
| Feature | `#feature` | A section / deliverable. |
| Idea | `#idea` | Body detail (default kind). |
| Context | `#context` | Background the model needs. |
| Constraint | `#constraint` | Guardrails — "don't touch", limits. |
| Question | `#question` | Open questions surfaced, *not* asserted as fact. |
| Output | `#output` | Desired output shape/format. |

**Edge labels become relations.** An unlabeled edge = plain containment (parent → child).
A labeled edge (`depends on`, `blocks`, `example of`) is rendered as an explicit relation
line so the structure survives linearization.

## 4. Validation pass (runs before every compile)

Errors block compilation; warnings are shown and can be overridden.

| Level | Check | Why |
|---|---|---|
| error | exactly one `#goal` node | the compiler needs one entry point |
| error | no empty node text | empty nodes compile to noise |
| error | goal has at least one outgoing edge | a lone goal isn't a map |
| warn | orphans (unreachable from goal) | silently dropping user content is the worst failure |
| warn | cycle detected | will be linearized by reference — say so |
| warn | no `#output` node | prompt has no output shape |
| warn | goal text has no done-criteria | mirrors prompt-coach `no-definition-of-done` |
| info | no `#constraint` node | mirrors `missing-guardrails` |

The warn/info rows deliberately mirror **prompt-coach's own rule vocabulary** — the same
house standard for what a good prompt contains, applied to a map instead of a sentence.
Orphans are never dropped: on override they compile into a trailing `## Unsorted notes`.

## 5. Compile algorithm (map → organized prompt)

Deterministic, no LLM. Given `nodes`, `edges`, `goal`:

1. **Index** — adjacency from `edges`; children sorted by canvas reading order (`y`, then `x`).
2. **Partition by kind** — `context`, `constraint`, `question`, `output` are pulled out as
   *sections*; `feature`/`idea` form the body tree.
3. **DFS from the goal** over the body, carrying depth → heading level (`##`, `###`, …),
   with a `visited` set.
4. **Cross-links & cycles** — a node reached a second time is **not duplicated**; it emits a
   reference (`→ see "Node title"`). The `visited` set makes cycles terminate. This is the
   whole trick to linearizing a general graph without losing or repeating content.
5. **Edge labels** — a labeled edge emits `- <label>: <target>` under the source.
6. **Orphans** — appended under `## Unsorted notes` (only if the user overrode the warning).
7. **Assemble** in fixed prompt-structure order:

```markdown
# <goal text>

## Context
...#context nodes...

## <Feature A>            ← DFS body, depth = heading level
### <child idea>
- depends on: <Feature B>     ← labeled edge
→ see "Feature B"             ← cross-link, not duplicated

## Constraints
- <#constraint nodes>

## Open questions
- <#question nodes>

## Output format
<#output nodes>
```

Ordering is fixed on purpose: task → context → body → constraints → questions → output
format is the structure the coach's own catalog pushes toward.

**Also emit** (optional toggle) a Mermaid `graph TD` block of the raw topology, so the
model sees the structure as well as the prose — the one genuinely good idea borrowed from
`obsidian-llm-plugin`.

## 6. Technical shape

Mirrors prompt-coach's dashboard, which is the proven in-repo pattern:

```
plugins/mindmap-prompt/
  .claude-plugin/plugin.json
  skills/mindmap-prompt/SKILL.md
  commands/{open,compile,list}.md
  scripts/
    serve.py         # stdlib http.server on 127.0.0.1, opens the page
    compile.py       # .canvas -> prompt (the algorithm above; unit-testable)
    validate.py      # the validation pass
    test-harness.py  # make test-mindmap
  page/mindmap.html  # self-contained: inline CSS + JS, hand-rolled SVG+DOM
```

- **Rendering: hand-rolled SVG (edges) + HTML/DOM (nodes), zero dependencies.** No CDN, no
  bundler, no vendored library. Cytoscape.js (MIT, standalone, offline-capable) is the
  fallback *only* if hand-rolled proves insufficient — it would not change the data model.
- **`compile.py` is the source of truth** for map→prompt, not the JS. That keeps the
  algorithm testable in the harness and usable headlessly (`compile.py map.canvas`), with
  the page as a thin editor over the same format.
- **State lives in the consuming repo**: `.claude/mindmap/*.canvas` (per the marketplace
  gotcha — an installed plugin's own dir is read-only cache).

## 7. Decisions (settled 2026-08-07)

1. **Name — `mindmap-prompt`.** Commands: `/mindmap-prompt:{open,compile,list}`.
2. **v1 scope — lean.** Four kinds: `goal / feature / idea / constraint`. **No** Mermaid
   block; `context` / `question` / `output` deferred until real use argues for them.
3. **Kind encoding — Markdown text tag** (`#goal …`), not a non-standard JSON key.
   Obsidian round-trips cleanly and diffs stay readable.
4. **Compile destination — all three**, clipboard default (file via `-o`, or straight into
   the session).
5. **One module, not two.** `compile.py` + `validate.py` collapsed into `scripts/mindmap.py`
   (`validate` / `compile` subcommands) — they share the graph index, and two files would
   have been ceremony.

### Correction to §5, made while building

The DFS in §5 was **wrong** and the golden fixture caught it. With a plain DFS, whichever
branch reaches a node first owns it — so a node wired *directly* to the goal could be
"stolen" by a long branch and buried three levels deep. The compiler builds a **BFS
spanning tree** instead: every node is owned by its *shortest-path* parent (ties broken by
reading order), then that tree renders depth-first. Direct children of the goal are always
top-level. Non-tree edges (cross-links, back-edges, second parents) render as
`→ see "..."` references. `t_bfs_ownership` in the harness is the regression guard.

## 7b. Visual language (added 2026-08-07, after the first build)

The first canvas rendered every node as an identical 260px bordered card with a
shadow and an uppercase kind chip. It worked, and it looked like a **flowchart**.
Screenshots of MindMeister and Lucidspark showed why that reads wrong: in a real
mind map, **hierarchy is carried visually**, and colour means *branch*, not *type*.

Adopted (MindMeister is the model — Alex's preference, and the clearer of the two):

| Depth | Rendering |
|---|---|
| 0 — the goal | no card at all: large 26px type + a `GOAL` eyebrow + a branch-coloured underline. It's the title of the map. |
| 1 — a branch | solid pill (`border-radius:999px`) filled with the branch hue, white text |
| 2+ — a leaf | bare text, high contrast, no box — the ribbon carries the colour |

- **One hue per top-level branch**, inherited by every descendant *and* its
  connectors, assigned in canvas reading order so it stays stable as the map moves.
  Six-hue palette; the colour says "same branch", nothing else.
- **Tapering ribbons, not strokes.** Connectors are *filled* bezier paths whose
  width shrinks from trunk (7px) to twig (1.8px), built by sampling the curve and
  offsetting along the normal. This is the signature element — a uniform grey
  stroke is what made the old canvas read as a diagram tool.
- **Side anchors** (exit right / enter left) so the map fans horizontally.
- **Junction dot** where a node's branches split.
- **Cross-links drawn at 38% opacity** so the spanning tree still reads as the
  structure — matching what the compiler actually does with them.
- **Kind survives without chips.** Only two kinds change compilation, so only two
  need a marker: `goal` (the eyebrow + root treatment) and `constraint` (dashed
  outline + `⊘`, at any depth — never colour alone). `feature` and `idea` compile
  identically today, so giving them distinct visuals would be a lie.
- **Nodes are auto-width** (`max-content`, capped) instead of a fixed 260px, so a
  three-word leaf stops looking as heavy as the goal.
- Accessibility held: kind never by colour alone, leaf text stays near-ink rather
  than tinted, light + dark both styled, full keyboard operation unchanged.

Two bugs surfaced only by *looking at screenshots*, not by the passing assertions:
a new sibling was positioned relative to its parent rather than the previous
sibling, and an empty-state `…` placeholder was a literal DOM character that got
picked up as the node's text when editing began (`## …Theme toggle` in the output).

## 8. Build order (once the above is settled)

1. `compile.py` + `validate.py` + harness fixtures — **the algorithm first, headless**.
   A `.canvas` fixture → expected `.md`, so the compiler is provably right before any UI.
2. `page/mindmap.html` — capture UX against the same format.
3. `serve.py` + `SKILL.md` + commands.
4. Docs page + `nav.adoc` + CHANGELOG + marketplace entry (docs are part of "done").
