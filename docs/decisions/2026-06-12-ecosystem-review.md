# Ecosystem review — dev-crew · brainstorm-panel · senior-prompts vs the field

**Date:** 2026-06-12 · **Status:** working draft (edit freely)
**Inputs:** venice-vr + unitrack learning logs (panel logs, dev-crew run logs, role registries) and a three-track web survey of comparable public Claude Code skills/plugins.

---

## TL;DR

1. **Both flagship skills are ahead of most of the public field.** brainstorm-panel combines three of the four rare deliberation mechanisms that *no* public project combines; dev-crew holds the rarest dev-workflow mechanism (an evidence-driven learning loop) plus two field-rare extras.
2. **The biggest improvement is structural, not textual:** machine-enforce dev-crew's gates with hooks (the venice failures — text-instead-of-file handoffs, fixture-green QA — are exactly what hook-enforced gates prevent; the evolving-claude-md lint hook already proves the pattern in-house).
3. **senior-prompts' design is validated as genuinely novel:** a per-repo markdown learnings log + compaction hook attached to a prompt pack exists nowhere else (the only pack+learning fusion, pro-workflow, uses an opaque global SQLite store).
4. brainstorm-panel's one real gap vs the field: **anti-groupthink instrumentation** — our logs celebrate "unanimous convergence"; the best council skills treat early unanimity as the highest-risk signal.
5. **Headline design change (follow-up review):** a two-layer role system, unified under `.claude/roles/`. Layer 1: both orchestrators run the **same roles-registry mechanism** — crew's at `.claude/roles/crew.md`, panel's at `.claude/roles/panel.md` (same rows, probationary→stable lifecycle, minting, per-role learnings). Layer 2: an optional **standalone `roles` plugin** adds shared core role files (`.claude/roles/<role>.md`) + solo invocation, with *shared identity, lane-scoped evolution* — each lane is physically its own single-writer file. Fixes the formation/evolution asymmetry, absorbs senior-prompts, and no public project has cross-context evolving roles. See § 3.0.

---

## 1 · Similar skills on the web

### 1.1 Multi-agent dev workflows (dev-crew's category)

| Project | Stars | Core design | Learn from | Weakness |
|---|---|---|---|---|
| [ruvnet/ruflo](https://github.com/ruvnet/ruflo) (ex claude-flow) | ~59k | Queen-led swarms, 100+ role agents, hierarchical/mesh topologies, Raft/Byzantine consensus, shared vector memory, ~210 MCP tools; SONA/ReasoningBank stores successful trajectories | Persistent cross-session agent memory — outcomes stored & retrieved | Enormous surface area; massive over-engineering for typical dev tasks |
| [wshobson/agents](https://github.com/wshobson/agents) | ~36k | Marketplace: 84 plugins / 192 agents / 156 skills; 16 orchestrators; explicit 5-tier model assignment per role; "PluginEval" statistical quality checks | Cost-aware model tiering per role; *evaluating* plugins statistically | Orchestration/handoffs thin — mostly a giant agent library; no learning loop |
| [EveryInc/compound-engineering-plugin](https://github.com/EveryInc/compound-engineering-plugin) | ~21k | Linear loop `/ce-strategy → /ce-brainstorm → /ce-plan → /ce-work → /ce-code-review → /ce-compound`; file-based markdown artifact handoffs; multi-agent review before merge | The `/ce-compound` step — persisting lessons into repo docs so each cycle starts smarter (cleanest learning loop in the ecosystem) | Strictly sequential single-track; no machine-enforced gates; Rails-flavored opinions |
| [aws-samples/sample-claude-code-agent-team](https://github.com/aws-samples/sample-claude-code-agent-team) | ~26 | Lead (Opus) writes specs → N coders/devops (Sonnet) **self-claim file-disjoint tasks from a shared queue** → N reviewers (Opus) verify in parallel; **three Python hooks machine-enforce gates** (completion blocked until the verify command actually ran); JSONL audit log | **Hook-enforced verification** — an agent *cannot* mark work done without proof of execution; file-disjoint partitioning for safe parallelism | AWS-flavored sample quality; no learning loop; tiny community |
| [Anthropic official plugins](https://github.com/anthropics/claude-code/blob/main/plugins/README.md) (feature-dev, code-review, pr-review-toolkit) | — | feature-dev = 7-phase sequential relay; code-review = 5 specialist agents in parallel with **confidence-based scoring to filter false positives** | Confidence scoring/aggregation across parallel reviewers to suppress noise | Review-centric; no full build/deploy crew; no persistence between runs |
| [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) | ~21.6k | 154 agents in 10 categories incl. meta/orchestration; per-agent tool-permission scoping | Granular tool permissions per role (QA can't write code) | A catalog, not a pipeline — orchestrators are prompt-only, no enforced handoffs/gates |

Also seen: [rohitg00/awesome-claude-code-toolkit](https://github.com/rohitg00/awesome-claude-code-toolkit) (7-agent SDLC pipeline with two-gate approval), barkain/claude-code-workflow-orchestration.

**Table stakes** (3+ projects): role-specialized agents · plan→build→review relay · file artifacts as handoff medium · parallel reviewer fan-out · Opus-for-judgment / Sonnet-for-labor splits.
**Rare differentiators:** (a) hook-enforced gates (AWS only) · (b) persisted learning loop (compound, ruflo) · (c) self-claiming file-disjoint task queues (AWS only) · (d) confidence-scored reviewer aggregation (Anthropic code-review) · (e) statistical workflow eval (wshobson).

### 1.2 Multi-perspective deliberation (brainstorm-panel's category)

| Project | Stars | Core design | Learn from | Weakness |
|---|---|---|---|---|
| [obra/superpowers](https://github.com/obra/superpowers) — `brainstorming` | ~225k (collection) | Deliberately NOT multi-persona: a single Socratic facilitator; hard gate — no implementation until the user approves a design | Ruthless gating discipline + placeholder/TBD self-review before handoff | Zero perspective diversity — one voice shares the user's blind spots |
| [0xNyk/council-of-high-intelligence](https://github.com/0xNyk/council-of-high-intelligence) | ~953 | 18 fixed historical personas in "polarity pairs"; modes full/quick/duo/triads; parallel analysis → cross-examination → crystallization → verdict that *leads with unresolved questions*; members routed across different model providers | **Enforced dissent:** dissent quota + novelty gate; >70% early agreement forces two members to steelman the opposing view | Fixed roster — personas not chosen from the task; theatrical overkill for small targets |
| [wan-huiyan/agent-review-panel](https://github.com/wan-huiyan/agent-review-panel) | ~20 | 4–6 seats auto-selected from content "signal groups"; user can override roster; 16-phase pipeline: parallel no-cross-talk review → private confidence → adversarial debate → *blind* final scoring → Opus judge → post-judge verification of judge-introduced findings; `--runs N` stability scoring | **Anti-groupthink instrumentation:** blind scoring, sycophancy detection, *unanimous agreement flagged as highest-risk* | Heavyweight fixed 16-phase march, no early exit; no per-repo memory |
| [ngmeyer/council-review](https://github.com/ngmeyer/council-review) (Karpathy "LLM Council" lineage) | 7 (archived → ngmeyer/skills) | 5 fixed *methodology* personas (Contrarian, First-Principles, Expansionist, Outsider, Executor); answers shuffled + anonymized before peer review; mandatory devil's-advocate pass; chairman may override majority | **Anonymized peer review + adaptive stopping** — halts when round-over-round position shift (KS test) stays below threshold for 2 rounds (~94% claimed cost reduction) | No user gating of roster; reasoning-style personas → shallow domain critique |
| [affaan-m/ECC — `council`](https://github.com/affaan-m/everything-claude-code/blob/main/skills/council/SKILL.md) | ~214k (collection) | Fixed quartet (Architect, Skeptic, Pragmatist, Critic); voices get *only* the question, minimal context (**anti-anchoring**); facilitator forms own position *before* reading them; rare per-repo persistence via `knowledge-ops` | Anti-anchoring via information starvation; explicit scope rule for *when a council is warranted at all* | Single round, no debate — disagreements catalogued, not stress-tested |
| [Michaelliv debate gist](https://gist.github.com/Michaelliv/4afd9429cdabea17e86e4df4f07b0718) · [MadeByTokens/claude-brainstorm](https://github.com/MadeByTokens/claude-brainstorm) | — / 3 | Gist: 3 *conflicting* personas, **user approves roster**, 5 debate phases, deliberately ends on tensions. claude-brainstorm: Six-Hats/SCAMPER with fork/back thread stack + hooks that *block code-writing* until `/brainstorm:done` | User-gated roster (gist); hook-enforced divergence + navigable idea tree (brainstorm) | In-context roleplay, no subagents (gist); rotating hats ≠ independent perspectives (brainstorm) |

**Common mechanisms:** parallel independent subagents → chairman/judge synthesis · mandated skeptic · consensus-vs-dissent verdict · fixed rosters · "no code until done" gates.
**Rare differentiators — the four nobody combines:** ① task-adaptive roster (agent-review-panel only) · ② user-gated roster (debate gist only) · ③ adaptive stopping (council-review only) · ④ per-repo learning (ECC, barely). **brainstorm-panel already has ①②④; only ③ is missing** (and its crude version — round cap + "stop on cosmetic-only rounds" — covers most of the value once 1-round is the default).

### 1.3 Persona prompt packs + learning loops (senior-prompts' category)

| Project | Stars | What it is | Learn from | Weakness |
|---|---|---|---|---|
| [obra/superpowers](https://github.com/obra/superpowers) | ~225k | Methodology-as-skills (`systematic-debugging`, `test-driven-development`, `verification-before-completion`…); auto-trigger via "Use when…" descriptions; short imperative rules ("The Iron Law: no fixes without root-cause investigation") | Imperative, short, enforceable rule-style prompts; trigger phrasing in descriptions | **No learning/memory capture at all** — purely procedural, stateless |
| [wshobson/commands](https://github.com/wshobson/commands) | ~2.5k | 57 slash commands split `workflows/` (multi-agent) vs `tools/` (single-purpose, e.g. `refactor-clean`, `debug-trace`); `$ARGUMENTS`; per-command `model:` pin | Namespaced invocation cleanly separating orchestration from utilities | Encyclopedic ~1,200-line prompts burn context; no automatic lessons capture |
| [anthropics/skills](https://github.com/anthropics/skills) (official) | ~150k | The reference for conventions: one folder per skill, `spec/` + `template/`, frontmatter description must say *what + when* | The spec + template + per-folder self-containment | Thin on engineering-discipline content; no memory |
| [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) | ~17.9k | 337 skills / 70+ commands / 30+ agents, multi-agent portability | Breadth, cross-agent portability | Curation/discovery; no learning loop |
| [rohitg00/pro-workflow](https://github.com/rohitg00/pro-workflow) | ~2.3k | **The only pack+learning fusion:** `/learn-rule` extracts corrections, `Stop` hook auto-captures `[LEARN]` blocks, pre/post-compact hooks preserve state, SessionStart replay — **but global SQLite** (`~/.pro-workflow/data.db`) | The full loop: capture → compaction survival → SessionStart replay; `/doctor` smoke-test UX | Heavyweight (SQLite + npm build); opaque vs a reviewable per-repo markdown log |
| [coleam00/claude-memory-compiler](https://github.com/coleam00/claude-memory-compiler) | ~1.1k | Memory-only: per-repo `.claude/`, SessionEnd+PreCompact hooks → daily logs → compiled knowledge articles + index injected at SessionStart | Two-stage raw-log → compiled-articles with a plain-markdown index (no RAG) | Python/uv dep + background jobs; ships no skills |

Ecosystem index: [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) (~46k).

**Verdict:** a per-repo **markdown** learnings log + compaction hook attached to a prompt pack is **rare to nonexistent** — senior-prompts' design is genuinely differentiated. Conventions worth adopting from the leaders: verb-first kebab-case names · "Use when <trigger>" description phrasing · short imperative prompt bodies over encyclopedias · category table + copy-paste install blocks in README (already done).

---

## 2 · Scorecards

### brainstorm-panel vs the four rare deliberation mechanisms

| Mechanism | Field holder | brainstorm-panel |
|---|---|---|
| Task-adaptive roster | agent-review-panel | ✅ Step 2 (derive seats from the work) |
| User-gated roster | debate gist | ✅ Step 4 (editable lineup, explicit approval) |
| Per-repo learning | ECC (barely) | ✅ Step 6 (panel log → graduation to CLAUDE.md) |
| Adaptive stopping | council-review (KS test) | ⚠️ crude only (round cap + "cosmetic-only" rule) — add a one-sentence "stop early if nothing material moved" rule on multi-round runs |

### dev-crew vs the five rare dev-workflow mechanisms

| Mechanism | Field holder | dev-crew |
|---|---|---|
| Persisted learning loop | compound-engineering, ruflo | ✅ **best-in-class** — log.md + roles.md graduation, steering-as-signal, evidence-based model *re-tiering* (unique) |
| Hook-enforced gates | AWS sample only | ❌ **the one real gap** — QA/deploy gates are prompt discipline; venice proved the failure mode |
| File-disjoint parallel devs / task queue | AWS sample only | ❌ deferred by design — `tech-lead` candidate role; mint when single-threaded dev is the bottleneck |
| Confidence-scored reviewer aggregation | Anthropic code-review | ❌ mostly N/A (one qa, not parallel reviewers) — belongs in **review-agents** instead |
| Statistical workflow eval | wshobson PluginEval | ❌ deliberate skip — cost ≫ benefit at this scale |

**Field-rare extras dev-crew already has:** editable roster checkpoint (almost every public pipeline is a fixed march) · steering taxonomy (classified mid-run injections that resume from the affected phase and feed the learning loop).

### Head-to-head (within the marketplace)

| | brainstorm-panel wins | dev-crew wins |
|---|---|---|
| Strength | Perspective diversity; task-fit roster; scope-kill before build (skeptic won 5×+ in unitrack, caught ~40% gold-plating in venice); roster gate | Durable file artifacts; hard deploy gate; steering taxonomy; learning loop that re-tiers models from evidence |
| Use for | Decide *what/whether*; stress-test plans; wide solution spaces | Build/ship a decided thing; verification against criteria + reality |
| Composition | Panel outcome = crew's task brief | Crew's contract files = panel's review subject (acceptance re-review) |

**senior-prompts (beta)** = the validated third tier: one persona, three orchestration levels — solo prompt (beta) → gated crew role → panel seat. These personas now **are** crew's roles, by the same name — `architect`, `debugger`, `optimizer`, `reviewer`, `refactorer`, `builder` — so one evolving role serves solo, crew, and panel alike; `builder` collapses architect+dev, and `skeptic` is the shared verifier across panel, crew, and research. The ecosystem's strongest pattern (VoltAgent agents seated into agent-review-panel) validates exactly this cross-pollination.

### The formation/evolution asymmetry (the gap §3.0 closes)

| | Formation (how the team is picked) | Evolution (do roles improve?) |
|---|---|---|
| **brainstorm-panel** | ✅ Dynamic — seats derived from the task's quality axes, per target | ❌ Ephemeral — every seat re-invented cold; accumulated seat wisdom ("art-collector reliably catches credibility-cheapening", "pair data-viz with designer on timeline targets") is buried in log prose, not attached to the seat |
| **dev-crew** | ❌ Static-ish — category → lineup lookup; venice's data/geo rosters had to be **hand-invented and seeded** because no category fit | ✅ Roles persist in `roles.md` with learnings, tiers, probationary→stable lifecycle, minting protocol |

Each skill has half of the right mechanism. Venice even shows the *same* persona living in both worlds with unconnected lessons: the art-historian was a crew role (molo run) and effectively a panel seat (catalog cleanup), its knowledge split across `roles.md` and the panel log.

---

## 3 · Proposed improvements (ranked)

### 3.0 · `roles` → NEW plugin (beta 0.1.0) — the structural headline

> **Status (implemented):** the role system shipped — `dev-crew`/`brainstorm-panel` at 1.1.0, and `roles` promoted directly to the **stable** catalog at 1.0.0 (the beta-staging phase was skipped by maintainer decision; the beta-channel narrative below is the original plan).

**The decision — two layers, one mechanism:**

- **Layer 1 (unconditional, in each orchestrator):** crew and panel run the **same roles-registry mechanism, under one roof**. Crew's registry moves to `.claude/roles/crew.md` (the rows-with-charter/status/learnings + minting mechanism it already has). Panel 1.1.0 replicates it exactly at `.claude/roles/panel.md` — so panel roles stop being ephemeral even standalone. Same row schema, same lifecycle, same name ("roles" — panel's graduated CLAUDE.md block was already called `## Panel roles`; "seats" was a distinction without a difference).
- **Layer 2 (optional `roles` plugin):** shared core role files (`.claude/roles/<role>.md`) consumed three ways — solo invocation, crew role, panel seat. Registry rows *link* to a shared role by name; identity and context-independent knowledge live once, context-specific bindings and lessons stay in each registry.

The orchestrators become two consumers among three — and **every file has exactly one writer** (crew owns `crew.md`, panel owns `panel.md`, the `roles` steward owns core files): no write contention, no lane-violation risk, no schema drift.

> **Why the move out of the skill directory is mandatory anyway:** a marketplace-installed plugin's skill dir is a **read-only cache** (`~/.claude/plugins/cache/…`). Venice's `roles.md`-next-to-the-skill pattern only worked because it was a manual `.claude/skills/` install. Any per-repo evolving registry must live in the repo — `.claude/roles/` is that home.

#### Packaging: a single dedicated plugin, not a mega-plugin

| Option | Verdict |
|---|---|
| Fold registry into dev-crew (it has `roles.md` already) | ❌ panel/solo users would need crew installed |
| One mega-plugin (roles + crew + panel) | ❌ kills per-skill versioning — the marketplace's founding convention; forces all-or-nothing installs |
| **Dedicated `roles` plugin + file-convention integration** | ✅ each plugin stays independently installable; coupling is a *convention, not a dependency* — crew/panel read & write `.claude/roles/` **if present**, work unchanged without it |

```
plugins/roles/
  .claude-plugin/plugin.json
  skills/as/SKILL.md              # /roles:as <role> <target> — run any registered role solo
  skills/<persona>/SKILL.md       # short-reference wrappers: /roles:debugger, /roles:builder, …
  seeds/<role>.md                 # seed role files, instantiated into the repo on first run
  hooks/hooks.json                # SessionStart: init .claude/roles/ + graduation audit
  scripts/roles-audit.py          # surfaces graduation candidates (annex → core), bloat warnings
```

#### Per-repo convention (canonical, evolves, in git)

```
.claude/roles/
  registry.md                     # index: name · charter · status · when-to-use (one line each)
  <role>.md                       # the role file — three ownership zones below
```

#### Schema — shared identity, lane-scoped evolution (lanes = separate files)

The **shared role file** (`.claude/roles/<role>.md`, written only by the `roles` steward + user-gated graduations) holds pure core:

```
## Charter · Body · When-to-use    ← IDENTITY — edits are DELIBERATE (user-gated, like crew re-tiering)
## Learnings (core)                ← entries arrive only by GRADUATION, never direct append
## Learnings (solo)                ← lessons from /roles:as runs (steward-owned, free-append)
```

The **context annexes are each consumer's own registry row** — not sections of a shared file:

| Lane | Lives in | Owned by | Holds |
|---|---|---|---|
| Crew | `.claude/roles/crew.md` row (+ `role: <name>` link) | dev-crew | model tier, tools, handoff contract, crew learnings |
| Panel | `.claude/roles/panel.md` row (+ `role: <name>` link) | brainstorm-panel | lens emphasis, pairing notes, panel learnings |
| Solo | shared role file's solo section | `roles` plugin | solo-run lessons |

A registry row without a `role:` link is a purely local role (works fine — that's standalone mode). Promoting a local role to shared = creating its core file from the row, user-gated.

**Why lanes (the venice evidence):** crew teaches a role *procedural* lessons ("write ARTREVIEW.md to the run dir", "implement the contract, flag don't absorb"); the panel teaches *epistemic* ones ("judge by title+depicts, never slug", "push back — disagreement is the point"). Merged naively, they contaminate: a solo run would obey run-dir procedures that don't exist; a crew dev-phase would adopt panel-style divergence that violates its contract. Some lessons even conflict by design. But context-independent knowledge ("title+depicts, never slug") belongs to everyone — that's what graduation is for.

**Three evolution rules:**
1. Each consumer free-appends **only to its own registry** (`crew.md` / `panel.md` / solo section); an invocation loads the shared core (if linked) + its own row only.
2. **Core learnings arrive by graduation** — when a lesson appears in 2+ lanes or is plainly context-independent, promote it to the shared core file and strike it from the local rows (the evolving-claude-md append→graduate→prune loop, one level down; the `roles` audit hook reads all three locations and surfaces candidates).
3. **Body/charter edits are deliberate** — either skill may *propose*, only the user applies (crew's re-tier protocol generalized). Everything is in git, so every change is reviewable.

Nothing here is a new mechanism: it composes evolving-claude-md's graduation, crew's gated re-tiering, and the panel's gate-edit-as-signal, applied to a role file.

#### What each consumer gains

- **Solo** — `/roles:as <role> <target>` + short-reference wrappers; the senior-prompts use case, now backed by evolving roles.
- **dev-crew** — its registry moves to `.claude/roles/crew.md` (same content, repo-writable home); gains the axis-driven *compose* path (unconditional). With the shared layer: rows link to shared roles, subagent prompts get core + crew row injected at delegation, and crew lessons can graduate to core.
- **brainstorm-panel** — gains `.claude/roles/panel.md`, **the same mechanism crew runs today**: per-role rows with charter, when-to-seat, probationary→stable lifecycle, minting, and per-role learnings (Step 6 writes wisdom to the row instead of burying it in log prose; the log keeps per-run records). With the shared layer: rows link to shared roles, panel lessons can graduate to core.

#### Standalone behavior — who owns the registry, and what happens without it

**Stewardship rule:** each skill creates and owns **its own registry file** under `.claude/roles/` (`crew.md`, `panel.md`) — that's Layer 1, no plugin dependency. The `roles` plugin stewards only the **shared core files** (`<role>.md`): it creates them (from seeds or user-gated promotions), ships the audit/graduation hook, and provides solo access. Consumers link to core files if present; they never create or edit them. One owner per file = no schema drift.

So, **brainstorm-panel installed alone (no `roles` plugin), at 1.1.0:**
- Fully self-sufficient — and now with crew-parity evolution. Step 2 derives seats dynamically AND proposes from `panel.md` first (stable roles whose when-to-seat matches); Step 4 gates the roster; Step 6 writes per-role learnings to `panel.md` rows and per-run records to the panel log; stable findings still graduate to CLAUDE.md `## Panel roles`.
- Nothing regresses, and the old gap (ephemeral seats, wisdom in log prose) is closed **without** the `roles` plugin — by the same mechanism crew uses.
- If `roles` is installed **later**, its hook inits the shared core; existing `panel.md` rows can link to (or be promoted into) shared roles. Late adoption costs nothing.

Same logic for dev-crew alone: `crew.md` is canonical — crew keeps its full evolution loop standalone; shared core files only change where role *identity and graduated knowledge* live when present. The integration sections in both 1.1.0 skills are literally one paragraph: "If shared role files exist: link rows to them and propose lessons for graduation. Otherwise: your registry is the whole story."

**No-downgrade principle:** a 1.1.0 capability gates on the registry **only if it intrinsically requires sharing**. The compose path, phase-gate hooks, and qa hardening ship unconditionally; the registry's exclusive value-add is only what sharing enables — cross-context learnings, solo invocation (`/roles:as`), and one talent pool across skills. Neither orchestrator is ever second-class standalone.

#### Migration path (phased, nothing breaks at any step)

| Phase | What ships | Breaking? |
|---|---|---|
| **0 — ship `roles` (beta)** | New plugin: seeds (the six senior-prompts bodies + a generic skeptic/reviewer/qa-practitioner), `/roles:as`, wrappers, init + audit hooks. Crew/panel untouched. Solo use works day one. | No |
| **1 — crew & panel 1.1.0** | Crew: registry moves to `.claude/roles/crew.md` + compose path (unconditional) + core linking (conditional). Panel: **`.claude/roles/panel.md` replicating crew's mechanism (unconditional)** + core linking (conditional). Without shared core files both are fully self-sufficient. | No |
| **2 — migrate the two history repos** (venice-vr, unitrack) | One-shot assisted migration per repo: (a) split `.claude/senior-prompts/learnings.md` by its skill tag into each shared role's solo section (entries are `- date — <skill> — lesson`, mechanical); (b) move the legacy `roles.md` to `.claude/roles/crew.md`, classifying learnings — procedural stays in the row, context-independent graduates to core; (c) extract seat wisdom from panel log prose into `panel.md` rows (assisted, user-reviewed). | No — additive rewrites, all in git |
| **3 — stabilize & promote** | After ≥3 runs per consumer validate the schema: promote `roles` beta→stable (`make promote`), retire `senior-prompts` from the beta catalog (its wrappers live on as `/roles:*`). | Only beta slash-names change (`/senior-prompts:*` → `/roles:*`) — acceptable, beta made no compat promise |

**Field position:** unique. The surveyed catalogs (VoltAgent's 154 agents, wshobson's 192) are static libraries; agent-review-panel selects dynamically but learns nothing. Nobody has roles that accumulate experience across orchestration contexts.

### dev-crew → 1.1.0

1. **Phase-gate hook** *(new — AWS pattern + in-house precedent from evolving-claude-md's lint hook)*: ship `check-handoffs.py` + `hooks/hooks.json` verifying the run dir at phase boundaries — PLAN.md/CONTRACT.md exist before dev runs; QA.md with per-criterion PASS before deployer runs. Converts the venice lessons from advice into guarantees.
2. Port venice's **Handoff discipline** section into the shipped registry seed (handoff = file on disk; conductor bridges if missing).
3. Strengthen `qa`: verify against the **real** gate/data, never fixtures that re-encode the logic under test; sweep all cases, exercise interactions (molo run + "one happy-path screenshot is not testing").
4. Add **ui-reviewer** to candidate roles (unitrack minted it from a standing steer; runs after qa on anything touching rendered pages).
5. **Axis-driven compose path** *(unconditional — no `roles` plugin required)*: when no category lineup fits, derive the task's failure axes and compose a roster panel-style, minting missing roles as probationary into `crew.md` (what venice did by hand for the data/geo rosters).
6. **Shared-core integration (§3.0)**: registry moves to `.claude/roles/crew.md` (mandatory for plugin installs — the skill dir is a read-only cache); if shared role files exist, rows link to them, subagent prompts get core + crew row injected, crew lessons become graduation candidates. Absent them, `crew.md` is the whole story — no capability is lost.
7. **Escalation protocol** *(new — unifies the qa-loop, Fable policy, debugger/lead candidates, and "go back" into one mechanism)*:
   - **`BLOCKED` handoff**: a role that can't meet its done-criteria writes its handoff file with `status: BLOCKED` + what it tried / why stuck / what it needs / suggested target. The phase-gate hook (item 1) accepts BLOCKED as valid (routes to conductor) while still rejecting a *missing* handoff — silent stumbles become impossible: deliver or declare. (Venice's fixture-green QA pass was a silent stumble; this is its structural fix.)
   - **Ladder (conductor-owned, each rung once per stumble):** ① clarify & retry same role (one retry) → ②/③ (diagnosis-driven, see below) → ④ re-plan: escalate *up the relay* to architect when the contract itself is wrong, downstream artifacts marked stale → ⑤ user: ladder exhausted, a genuine user decision (scope/topology forks skip straight here), or a cost gate.
   - **② re-tier vs ③ re-role is a diagnosis, not a sequence** — the BLOCKED report's "why stuck" decides. *Capability gap* (role is right, model is short: real progress, repeated near-misses, work exceeds depth) → **② re-tier** same role (sonnet→opus; →Fable only via the gated policy); a different role would hit the same ceiling. *Ownership gap* (model is fine, role is wrong: doing work its charter doesn't own — dev looping on root-cause is debugger's diagnosis job; cross-subsystem → lead; or needs tools its scope denies) → **③ re-role** to the failure-class owner (mint probationary via the compose path if missing); a heavier model here is a more expensive flail. Continuity heuristic: approach sound but execution short → re-tier (preserves artifacts, one variable changed); approach itself suspect → re-role (fresh method). Unclear → re-tier first (keeps lane discipline; early jumps to `lead` import scope creep). The registry already encodes both cases: art-historian "opus-eligible for hard attribution calls" (re-tier in lane) vs "debugger escalates into lead if it spans subsystems" (re-role by failure class).
   - **Feeds the learning loop**: every escalation logged (`escalation:` in the run entry); repeated rung-② hits = permanent re-tier evidence; recurring rung-③ hops to a missing owner = the mint-a-new-role trigger.

### brainstorm-panel → 1.1.0

1. Restraint/skeptic seated **by default** (strongest cross-repo signal: 7+ wins).
2. **Unanimity → steelman guard** *(new — council-of-high-intelligence / agent-review-panel)*: if all seats agree in round 1, the skeptic must steelman the opposing view before the director accepts.
3. Default = swarm→director-led, **1 round**; reserve 3–4 rounds for irreversible plan-locks with an explicit cost note (venice's 4-round run ≈ 18 deep passes).
4. Pre-propose the two seats users kept adding: practitioner/QA-consumer + "buildable in THIS codebase" engineer.
5. **Acceptance re-review mode** *(new — both repos' logs)*: re-convene the same roster, 1 round, on the implemented subset.
6. **Evidence-capture step** for artifact targets: screenshots/probes as panel input; sign-off requires evidence (the venice "shipped-then-broken" lesson).
7. Standing user preferences outrank a role's veto (the WebJars lesson) — read CLAUDE.md/memory first.
8. *(Optional, one sentence)* adaptive stopping on multi-round runs: stop early when nothing material moved between rounds.
9. **Panel roles registry `.claude/roles/panel.md`** *(unconditional — replicates crew's mechanism)*: per-role rows (charter · when-to-seat · status probationary→stable · learnings), minting protocol, Step 2 proposes from it first, Step 6 writes per-role wisdom to rows (log keeps per-run records). Same schema and lifecycle as crew's registry.
10. **Shared-core integration (§3.0)**: if shared role files exist, `panel.md` rows link to them by name; panel lessons become graduation candidates for the core. Absent them, `panel.md` is fully self-sufficient.

### senior-prompts → absorbed into `roles` (supersedes the earlier 0.2.0 plan)

1. The six persona bodies become the `roles` plugin's **seed role files**; short-reference invocation lives on as `/roles:debugger` etc., plus the generic `/roles:as <role> <target>`.
2. The per-repo markdown learning loop — field-validated as a differentiator (keep markdown, not SQLite; read-on-use, not SessionStart injection) — generalizes from one pack-wide `learnings.md` into **per-role solo annexes**; the compress hook becomes the registry's graduation/bloat audit.
3. `senior-prompts` retires from the beta catalog at Phase 3 — it never left beta, so no compatibility promise is broken.

### review-agents (note)

- Consider Anthropic-style **confidence scoring**: have the three reviewers rate finding confidence; suppress low-confidence findings.

### Deliberate skips

ruflo-style swarm topologies/consensus protocols (over-engineering) · 16-phase fixed pipelines · blind/anonymized scoring (wrong scale) · statistical PluginEval (cost ≫ benefit at this catalog size).

---

## 3.5 · The learning lifecycle — feeding evolution back to the marketplace

The open design question: per-repo evolution strands hard-won learnings in individual repos; the
shipped seeds never improve. The answer is **harvest, don't sync** — most learnings are *meant* to stay
local (repo-specific quirks); only the genuinely universal few belong upstream, and lifting them is the
existing graduation ladder with one more rung.

| Level | Lesson lives in | Promotion gate | Status |
|---|---|---|---|
| 1 · Observed | a run → local lane (solo/crew/panel annex) | free-append | built |
| 2 · Repo-core | `.claude/roles/<role>.md` core (recurs / context-independent in this repo) | user-gated graduation | built |
| 3 · **Upstream** | the marketplace **seed** (`plugins/<p>/.../role.md`) | **a PR** — the missing rung | **gap** |
| 4 · Shipped | every install, on update | version bump | built |

**Why a PR is the right boundary, not a limitation:** the marketplace is public, versioned, and curated —
a contribution must be reviewed and version-bumped. The PR review *is* the "is this universal?" judgment,
the same human gate every other graduation has. Over-promoting local quirks would pollute the seed for
everyone, so the decision stays human.

**Strength signal — cross-repo recurrence:** a single repo asserting universality is weak; the same
learning independently graduating to core in ≥2 repos is the strong signal (the 3×-recurrence rule applied
across repos instead of within one), and it is mechanically detectable.

**Proposed mechanism — `make harvest` (maintainer-side, next phase):**
1. Read-only scan of a configured set of repos' `.claude/roles/*.md` (+ `crew.md`/`panel.md` learnings, CLAUDE.md D&L).
2. Cluster by role + similar text; flag learnings recurring across repos or tagged universal.
3. Draft a PR to the marketplace adding the lesson to the relevant seed `role.md` `## Learnings (core)` + a version bump.
4. Human review at the PR = the curation gate; CI + `make validate` guard the rest.

Automate detection + drafting (cheap, evidence-backed); keep the decision human. Note the marketplace
**dogfoods its own plugins**, so its own `.claude/roles/` learnings graduate into its own seeds directly
— only cross-repo harvest needs the PR path. Tracked as a follow-up to the role-system epic (issue #2).

## 3.6 · The three orchestrators + `roles` — what's different

`roles` is **not an orchestrator** — it is the *substrate*: the shared, evolving talent pool plus solo
invocation (`/roles:as`). It's the **noun** the three **verbs** operate on. The three orchestrators each
compose a task-fit roster of those roles, but differ on every axis below.

| Axis | brainstorm-panel — **decide** | dev-crew — **deliver** | research-sweep — **discover** |
|---|---|---|---|
| Produces | a judgment / decision (advisory, no artifact shipped) | a shipped target, gated | verified, cited findings |
| Roles relate by | **disagreement** — the clash is the point | **handoff** — sequential, each builds on the last | **independence** — disjoint coverage, no clash |
| Flow | parallel diverge → converge | sequential gated relay | parallel fan-out → synthesize + verify |
| Compose roles from | quality axes (perspectives) | the delivery target (functions) | the information space (coverage angles) |
| Guards against | groupthink / blind spots (unanimity = red flag) | shipping broken / unverified work | incomplete coverage + unverified facts |

Two properties tie them together:

* **They chain.** research (discover the facts) → panel (decide what to do) → crew (deliver it).
* **They share roles.** The `skeptic` is a panel seat, a crew adversarial check, *and* a research
  fact-verifier — one evolving persona, three contexts. That cross-context reuse is exactly what the
  shared core (§3.0) exists for; research-sweep is the third consumer that proves it.

**Decision — research-sweep's coverage roles are named, evolving roles** (not ad-hoc angles), seeded as
generic *archetypes* (`entity-scout`, `timeline-scout`, `source-scout`, `container-scout`) with probationary minting
for corpus-specific angles — the crew seed+mint model. The verifier (shared `skeptic`) and a synthesizer
are persistent core roles. This makes research-sweep a full role-system consumer: registry
`.claude/roles/research.md`, dynamic composition from the information space, per-repo learning,
shared-core linking, self-sufficient without the `roles` plugin (no-downgrade). The registry hook's
`CONSUMER_FILES` gains `research.md`, and graduation fires when a role appears in **2+ of the three**
consumer registries.

## 4 · Evidence base (local)

- `venice-vr/.claude/brainstorm-panel/log.md` — 7 panel runs (incl. the 4-round plan-lock and the Time Slider series)
- `venice-vr/.claude/skills/dev-crew/{log.md,roles.md}` — molo run defects → handoff-discipline + verify-against-reality steers; data/geo rosters (repo-specific, **not** ported)
- `unitrack/.claude/brainstorm-panel/log.md` — 8 runs; Restraint-Skeptic 5×+ wins; QA+SDET seat graduation; WebJars preference-outranks-veto
- `unitrack/.claude/skills/dev-crew/{log.md,roles.md}` — ui-reviewer minted mid-run from a standing steer
