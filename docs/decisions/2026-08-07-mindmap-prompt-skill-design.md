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

## 7. Open questions (for Alex)

1. **Name** — `mindmap-prompt`, `map-to-prompt`, or `idea-map`? (Convention: descriptive
   kebab-case, verb-first for actions, ≤3 words.)
2. **Compile destination** — clipboard only, write to a file, or feed straight into the
   session as the next prompt? (Leaning: all three, clipboard default.)
3. **Kind encoding** — the `#goal` text-tag above (Obsidian-safe) vs. a non-standard
   `"kind"` key on the node (cleaner, but breaks strict-spec round-trips). Leaning text-tag.
4. **Scope of v1** — is the Mermaid topology block and the `question`/`output` kinds v1, or
   does v1 ship just goal/feature/idea/constraint?

## 8. Build order (once the above is settled)

1. `compile.py` + `validate.py` + harness fixtures — **the algorithm first, headless**.
   A `.canvas` fixture → expected `.md`, so the compiler is provably right before any UI.
2. `page/mindmap.html` — capture UX against the same format.
3. `serve.py` + `SKILL.md` + commands.
4. Docs page + `nav.adoc` + CHANGELOG + marketplace entry (docs are part of "done").
