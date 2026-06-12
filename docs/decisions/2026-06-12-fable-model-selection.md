# Fable model-selection for the role-system orchestrators — design draft

**Date:** 2026-06-12 · **Status:** WORKING DRAFT (open — edit freely; no decision yet)
**Scope:** how to decide which seat(s) in `dev-crew`, `brainstorm-panel`, and `research-sweep` should
run on the **Fable** tier. Backlog tracking: issue #8.

---

## 1 · The question

Fable is the top, most-capable tier (~2× Opus quota; API-rate credits after 2026-06-22). Spending it on
*every* seat is wasteful and, for a panel, can be actively harmful (see §5). So: **which single seat (or
few) earns Fable, per orchestrator?** The answer turns out not to be one rule — it depends on where the
run *bottlenecks*.

## 2 · How to run a seat on Fable today (mechanics)

The orchestrator (the main session) chooses each subagent's model when it spawns it via the Task tool.

1. **Per-seat, at the roster checkpoint** *(recommended; per-seat control)* — tell the skill "run the
   verifier on Fable"; the orchestrator passes `model: fable` to that Task call.
2. **`CLAUDE_CODE_SUBAGENT_MODEL`** env var — forces *every* subagent onto one model (blunt/global;
   collapses any per-role tiering).
3. **Whole session on Fable** (`/model`) — orchestrator *and* seats; most expensive.

**Caveats (apply to all three):** Fable ≈ 2× Opus quota, API-rate credits after 2026-06-22; safety
classifiers (cyber/bio) can silently reroute a Fable request to Opus — so a "Fable seat" on a
security/bio-adjacent topic may quietly *be* Opus (verify in the transcript); requires Claude Code
v2.1.170+; not selectable under zero-data-retention.

## 3 · The three Fable archetypes

Fable buys three *different* things, which map to three different seats:

| Bottleneck (the run's weak link) | Fable seat | What Fable buys |
|---|---|---|
| Ideas / designs aren't deep enough | a **generator** — architect, a "visionary" panel seat, the synthesizer | **raises the ceiling** — produces ideas/designs the cheaper seats wouldn't |
| Conclusions aren't trustworthy | the **skeptic / verifier** (also crew's `lead`) | **catches what others miss** — refutes, finds the flaw, self-verifies |
| The *coordination itself* is hard | the **conductor / director** | **better orchestration** — roster composition, routing (re-tier vs re-role), synthesis, gate calls |

There is **no single rule** because the bottleneck differs by orchestrator and by run. You fund the seat
sitting at *this run's* weak link.

## 4 · Why "skeptic only" is insufficient

The skeptic is the cleanest *single* answer (it's the one role shared across all three orchestrators, and
verification is always valuable). **But a skeptic only prunes — it never raises the ceiling.** A Fable
skeptic critiquing Opus-generated ideas gives Fable-quality *filtering* of Opus-quality *thinking*; you
never get the idea the lesser seats couldn't produce. So **generation-bound work needs Fable on a
generator**, not (only) the skeptic.

## 5 · Per-orchestrator analysis (by bottleneck)

### brainstorm-panel — *generation-bound*
Its job is producing strong ideas, so the ceiling is the best idea generated → favor a Fable
**generator**. **Critical nuance:** don't Fable *all* seats — Fable's investigate-and-converge tendency
*reduces* the diversity that is the panel's whole point. The move is **one** Fable "deep / wildcard"
generator that adds a depth dimension, alongside diverse Opus seats for breadth, plus a skeptic to prune.
Director-on-Fable only on orchestration-heavy runs (§6).

### dev-crew — *design-bound*
Quality bottlenecks on the design. dev-crew's *existing* policy already makes the **architect** (a
generator) Fable-eligible — and `lead` (deep root-cause = verifier/investigator). Conductor is **not**
Fable by default (cost). So crew already encodes "Fable on the generator + the deep investigator, gated."

### research-sweep — *verification / coverage-bound*
The coverage scouts are mechanical breadth (never Fable). The leverage is the **skeptic-verifier** and,
secondarily, the **synthesizer**. This is the one orchestrator where "skeptic gets Fable" is close to the
whole answer.

## 6 · The conductor tension — cost vs. leverage

Early heuristic: "never Fable the conductor — it's the always-on seat that emits the most tokens." That
conflates **token volume** with **token value**. The conductor emits the *most* tokens (most expensive)
**and** the *highest-leverage* ones (roster composition, routing, synthesis ripple through the whole
run). Managing a big multi-agent run is literally Fable's stated sweet spot (long-horizon, many parts,
investigate-before-acting).

**Reconciliation — a condition, not a blanket:** Fable on the conductor pays **only when the orchestration
itself is the hard part** — many roles, dynamic re-rostering, multiple rounds, heavy synthesis (e.g.
venice's 7-seat / 4-round plan-lock). On a small run (3 seats, 1 round) the conductor's job is easy and
Fable there is pure waste.

> Honesty flag: "Fable is good at *managing agents*" is plausible and matches its design, but it's a
> claim to **verify against real runs** before baking conductor-on-Fable into policy — treat it as a
> model-fit hunch (the dev-crew log already treats every such hunch as something to confirm, not assume).

## 7 · Open questions (to resolve before speccing)

1. **One Fable seat or two?** Generation-bound work may want *both* a deep generator and a deep verifier;
   is the extra Fable seat worth 2× again?
2. **Property of the role, or per-row field?** Cleaner than a `model` field on every registry row may be a
   **Fable-eligibility flag on the shared core roles** (`skeptic`, `architect`, `lead`, plus a panel
   "visionary"), gated — one property on a few shared roles instead of a tier dial everywhere.
3. **Reliability of a *stored* Fable tier** given the safety-classifier reroute — unreliable for
   security/bio domains. Acceptable for a per-run ask; questionable as a persisted default.
4. **Does Fable actually orchestrate better?** Verify on real multi-agent runs (§6 flag) before §5/§6
   defaults are set.
5. **Economics after 2026-06-22** (API-rate credits) — argues for keeping Fable a gated, opt-in
   escalation, never a quiet registry default.

## 8 · Implementation sketch (feeds issue #8)

- **Gated escalation, mirroring dev-crew:** Fable is *never* auto-selected; it's proposed at the roster
  checkpoint with an explicit ~2× cost line, defaulting the same seat to Opus so declining is the easy
  path.
- **Where Fable-eligibility lives:** lean toward a **role-level flag on shared core roles** (skeptic,
  architect, lead, a panel visionary) over a per-row `model` field on every consumer registry — fewer
  knobs, propagates via the shared core, matches the "one persona, many contexts" model.
- **Per-orchestrator default seat** from §5: panel → a deep generator (+ optional skeptic); crew →
  architect/lead (already); research → skeptic-verifier (+ optional synthesizer); conductor → only on
  orchestration-heavy runs (§6), gated.

## 9 · Decision

**TBD** — left open for further work. This draft captures the reasoning; the choice of (a) one vs two
Fable seats, (b) role-flag vs per-row field, and (c) whether to allow conductor-on-Fable at all is still
to be made.
