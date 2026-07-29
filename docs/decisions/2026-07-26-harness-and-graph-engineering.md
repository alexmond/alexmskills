# prompt-coach — harness engineering & graph engineering applicability

**Status:** research / design note, for a future review. Not yet scheduled work.
**Date:** 2026-07-26. **Tracking:** GitHub issue (see bottom).

Research question: do the two 2026 agent-engineering paradigms — **harness
engineering** and **graph engineering** — apply to prompt-coach, and where?

**Verdict up front:** harness engineering fits almost perfectly (prompt-coach *is*
a harness component); graph engineering fits *selectively* — very well for the rule
catalog, not for the per-prompt hot path.

## The two terms, grounded in current (2026) usage

**Harness engineering** — engineering the scaffolding *around a fixed model*: the
loop, context builder, tool registry, guardrails, budgets, memory, tracing, evals.
The model is a stateless predictor; reliability is won or lost in the harness. The
load-bearing finding: **~65% of enterprise AI failures are "harness defects" —
context drift, schema misalignment, state degradation — not model reasoning.** An
*eval harness* (deterministic assertion engine over a labeled set) is the defense.

**Graph engineering** — designing around *explicit typed graphs* instead of flat
text. Two senses: (a) knowledge as nodes + typed edges an agent traverses;
(b) graph-based orchestration — nodes do work, typed edges route, shared state
flows (LangGraph-style). Emerging edge: *replace free-form skill prose with directed
execution graphs — discrete steps as nodes backed by deterministic scripts, typed
I/O edges, schema-validated YAML.*

## Why the fit is natural: prompt-coach is itself a harness

The coach is Claude Code's instruction-manager + context-builder + guardrail layer —
it intercepts `UserPromptSubmit` and injects `additionalContext`. It already
implements much of the "15-module" harness component model:

| Harness module | Coach today |
|---|---|
| Instruction manager | 42-rule catalog |
| Context builder | collaborator rewrite via `additionalContext` |
| Budget tracker | `max_active_rules`, fatigue cap (`max_nudges_per_window`) |
| Permission resolver | `enabled`, `disabled_rules`, `collaborator_gate` |
| Memory | mastery ledger / `state.json` |
| Observability | `log.md`, stats, web dashboard, acceptance ledger |

## Harness engineering — HIGH applicability, two gaps

### 1. A real eval harness (highest ROI)

`test-harness.py` checks behavior, but there is no *golden precision set*. The
coach's false positives **are** its harness defects — the vague-reference-on-resolved-
reference FP is textbook "context drift"; the mastery double-count already fixed was
"state degradation." The corpus already exists: the **381 cross-repo logged prompts**
(the 2026-07-19 evaluation). Label them (fire / veto / expected rule) and run per-rule
**precision/recall as a release gate**. Turns whack-a-mole FP fixing into measured
regression. **Do this first — it is the unlock for the other three.**

### 2. Safe model-in-the-loop fallback

`llm_fallback` is stubbed. Harness engineering says how to add it without wrecking
determinism, and the research backs the existing instinct: *deterministic assertion
engines are decisive for safety-critical; LLM-based eval scored 0% on paradox
detection.* So — **keep regex as the gate, use a cheap structured-output model only
to widen recall when regex is uncertain, cache it, never sole arbiter.** The eval
harness (#1) is what proves whether it helps.

## Graph engineering — SELECTIVE, one high-value coach-specific use

### 3. Make the implicit rule graph explicit (the real win)

The rules already form a graph, scattered across code today:

- **veto edges** (the goal-vs-loop bleed fixed with a hand-coded veto regex)
- **co-fire edges** (rules that surface together)
- **mirror edges** (rule ↔ its positive detector)
- **tier-succession edges** (mastering an L1 rule unlocks an L2)
- **source edges** (rule → citation → principle, the `_EXTRA_SOURCES` dict)

As one typed graph this would: drive **activation selection** when several rules
fire (suppress dominated nodes instead of a flat `max_active_rules` cap); make
**veto propagation systematic** instead of per-rule regexes (that is most of the
recent FP fixes); and turn **mastery** from flat tier ints into graph traversal.
Graph engineering applied to the *catalog itself* — directly attacks the FP-
maintenance burden.

### 4. Directed execution graph for the Java MCP server

The pipeline (detect → gate → rewrite → record acceptance → update mastery) is
already a state machine. The "deterministic scripts as nodes, typed I/O edges,
schema-validated YAML" pattern is the right shape for the **planned server rewrite** —
both paradigms converge here. Not worth retrofitting into the Python hook.

### Where graph engineering does NOT apply

Keep the per-prompt path ~10ms deterministic regex. No graph traversal, no LLM, on
the critical path — graph work belongs in the *config/offline* layer (catalog
structure, activation policy, server orchestration), never per-keystroke.

## Prioritized plan

1. **Eval harness** over the 381-prompt corpus → per-rule precision/recall + release
   gate. *(harness; uses data already in hand)*
2. **Explicit rule-relationship graph** → systematic veto/activation/mastery.
   *(graph; kills FP whack-a-mole)*
3. **Coach pipeline as a directed execution graph** in the Java MCP server.
   *(both converge)*
4. **Safe LLM fallback**, gated by the eval harness. *(harness; already stubbed)*

The two paradigms are complementary: harness engineering upgrades *how the coach is
measured and controlled*; graph engineering upgrades *how the rule catalog is
structured*. The eval harness is the foundation — a rule graph or an LLM fallback
cannot be added safely without a precision gate to prove they helped.

## Sources

- [Agent harness — Wikipedia](https://en.wikipedia.org/wiki/Agent_harness)
- [Harness Engineering (AI Magicx)](https://www.aimagicx.com/blog/harness-engineering-replacing-prompt-engineering-2026)
- [Agent Harness Engineering — the AI Control Plane](https://medium.com/@adnanmasood/agent-harness-engineering-the-rise-of-the-ai-control-plane-938ead884b1d)
- [From Prompts to Contracts (arXiv 2607.08028)](https://arxiv.org/pdf/2607.08028)
- [awesome-harness-engineering](https://github.com/ai-boost/awesome-harness-engineering)
- [Eval harness — DeepEval](https://deepeval.com/blog/what-is-an-eval-harness)
- [Harnessing Agent Skills: directed execution graphs (arXiv 2606.20631)](https://arxiv.org/pdf/2606.20631)
- [Graphs vs. Loops — agentic orchestration 2026](https://explainx.ai/blog/graphs-vs-loops-agentic-ai-debate-linear-andrew-ng-2026)
- [Graph Engineering for AI Agents (Eigent)](https://www.eigent.ai/blog/graph-engineering-ai-agents)
- [What Is Graph Engineering (The AI Operator)](https://theaioperator.io/p/what-is-graph-engineering-a-field)
