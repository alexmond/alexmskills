# prompt-coach — sources

The rule catalog is grounded in a mix of first-party guidance (Anthropic) and independent
prompt-engineering practice. Each rule in [`scripts/analyze-prompt.py`](../scripts/analyze-prompt.py)
carries a `sources=[...]` list pointing back to one or more of these. If a rule doesn't have at
least two, it isn't ready to ship.

## Primary (first-party)

- **Anthropic — Prompt engineering overview.** The umbrella guide.
  <https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview>
- **Anthropic — Be clear and direct.** Names the anti-pattern behind vague reference /
  no-definition-of-done / improve-without-metric / no-rubric.
  <https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/be-clear-and-direct>
- **Anthropic — Chain complex prompts.** Grounds compound-tasks, missing-guardrails,
  no-adversarial-check, retry-without-diagnosis, unbounded-iteration.
  <https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/chain-prompts>
- **Anthropic — Let Claude think (chain of thought).** Grounds no-chain-of-thought.
  <https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/chain-of-thought>
- **Anthropic — Multishot prompting (give examples).** Grounds no-few-shot.
  <https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/multishot-prompting>
- **Claude Code — Best practices** (engineering post). Grounds the L5 tool-native rules
  (plan mode, TaskCreate, subagents, roles, brainstorm-panel, Workflow).
  <https://www.anthropic.com/engineering/claude-code-best-practices>
- **Claude Code — Hooks, subagents, and the Task tool** (docs). Grounds L5 tool-delegation
  rules operationally.
  <https://docs.anthropic.com/en/docs/claude-code/hooks>

## Independent

- **OpenAI — Prompt engineering guide.** Convergent guidance on shape-of-output specification and
  measurable-improvement asks. Cross-vendor sanity check.
  <https://platform.openai.com/docs/guides/prompt-engineering>
- **Simon Willison — Prompt engineering notes.** Working practitioner's take on being specific,
  showing examples, and iterating.
  <https://simonwillison.net/tags/promptengineering/>
- **Schulhoff et al. — The Prompt Report (2024).** Systematic survey of prompting techniques and
  their empirical effects; anchor for "why does this actually matter" per rule.
  <https://arxiv.org/abs/2406.06608>
- **Wei et al. — Chain-of-Thought prompting elicits reasoning in large language models (2022).**
  The canonical CoT paper. Cited by no-chain-of-thought.
  <https://arxiv.org/abs/2201.11903>
- **Brown et al. — Language models are few-shot learners (2020).** The GPT-3 paper that made
  few-shot in-context learning a first-class technique. Cited by no-few-shot.
  <https://arxiv.org/abs/2005.14165>
- **LangChain — Plan-and-execute agents.** Argues for generating a complete plan up front and
  executing steps without consulting the agent after each action — fewer LLM calls, lower cost
  than step-at-a-time ReAct. Cited by incremental-routing.
  <https://www.langchain.com/blog/planning-agents>

## Encouragement layer (praise design)

The v0.3 praise layer draws from behavioral-science literature on effective feedback and habit
formation. Sources — cited on the specific positive detectors:

- **Mueller & Dweck (1998) — "Praise for intelligence can undermine children's motivation and
  performance."** The seminal study on *process praise* beating *trait praise*.
  <https://psycnet.apa.org/doi/10.1037/0022-3514.75.1.33>
- **Dweck (2006) — *Mindset: The New Psychology of Success.*** The mindset framing behind
  process-focused praise. <https://mindsetworks.com/>
- **Fogg (2019) — *Tiny Habits: The Small Changes That Change Everything.*** Grounds
  first-after-fire recognition and celebration-of-small-wins as habit-formation mechanics.
  <https://tinyhabits.com/>
- **Brophy (1981) — *Teacher Praise: A Functional Analysis.*** The foundational analysis of what
  makes praise effective (specific, immediate, credible, describes the behavior).
  <https://journals.sagepub.com/doi/10.3102/00346543051001005>
- **Deci & Ryan (2000) — Self-determination theory.** Grounds *autonomy-supportive* framing —
  informational praise beats controlling praise.  <https://selfdeterminationtheory.org/>
- **Kohn (1993) — *Punished by Rewards.*** The "don't dilute the correction" principle behind
  never-praise-on-a-nudged-prompt and the sparing default ratio (1-in-10).
  <https://www.alfiekohn.org/punished-rewards/>

## Skill-awareness (L6)

The L6 tier catches "should this be a skill?" moments — reaching for existing skills, and noticing
patterns worth abstracting. Sources:

- **Fowler (2018) — *Refactoring* (2nd ed.).** The rule of three (refactor on 3rd occurrence).
  <https://martinfowler.com/books/refactoring.html>
- **Kent Beck / XP — YAGNI.** Don't abstract on N=1; do abstract on N=3.
  <http://www.extremeprogramming.org/rules/early.html>
- **Anthropic — Claude Code Skills docs.** Ground truth on what a skill is / when a description
  becomes a skill. <https://docs.anthropic.com/en/docs/claude-code/skills>
- **McIlroy — Unix philosophy.** Composition over duplication; small tools that do one thing well.
  <https://en.wikipedia.org/wiki/Unix_philosophy>
- **Norman — *The Design of Everyday Things*.** Discoverability over memorability — the user
  shouldn't have to remember what skills exist.
  <https://mitpress.mit.edu/9780262525671/the-design-of-everyday-things/>

## How to add a source

1. Add the tuple `SRC_<NAME> = ("Title", "URL")` at the top of the rule catalog.
2. Reference it from at least two rules — sources not cited from ≥2 rules are candidates for
   removal (avoid appendix bloat).
3. Add it here with one line on what it uniquely contributes; if it's redundant with an existing
   source, either replace or explain the redundancy.

## How to add a rule

1. Write a `check(prompt: str) -> bool` heuristic. Regex-first; no network, no LLM.
2. Pick a tier — L1 (fundamentals every prompt should get right), L2 (intermediate), L3 (advanced).
3. Cite ≥2 sources. If you can only cite one, the rule is probably opinion-of-one — sharpen or cut.
4. Ship at v0.x; monitor `log.md` for false-positive rate over ~30 prompts before graduating a
   rule into a new tier default.
