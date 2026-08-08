# Rule sources

Every rule the linter ships traces to published skill-authoring guidance. This file
records which source, what it says, and — where the sources disagree — how the
conflict is resolved.

Read this before changing a rule. A rule whose provenance is unclear will
eventually be dismissed as opinion, and once one rule is dismissed the rest lose
their authority too.

## Contents

- [The three sources](#the-three-sources)
- [Where the sources conflict](#where-the-sources-conflict)
- [Rule provenance](#rule-provenance)
- [Guidance deliberately not enforced](#guidance-deliberately-not-enforced)

## The three sources

| Short name | What it is |
|---|---|
| **skill-creator** | Anthropic's official skill-creation skill. Its centre of gravity is an eval loop (draft → run with and without the skill → human review → rewrite), plus a description optimiser that tests trigger accuracy on 20 should/should-not queries. |
| **skill-development** | Guidance for skills shipped inside Claude Code plugins. Strongest on writing style and a concrete validation checklist. |
| **writing-skills** | A TDD-flavoured treatment. Strongest on discovery — its "Skill Discovery Optimization" section is the most specific published material on what a description should contain. |

All three agree on the fundamentals: `name` + `description` frontmatter, the
description is the sole triggering mechanism, keep SKILL.md lean and push detail
into `references/`, write imperatively, and test the thing.

## Where the sources conflict

Two direct contradictions surfaced while building this. Both are resolved in
favour of a narrower rule than either source states, because a linter that
enforces a contested rule is worse than one that enforces only the agreed part.

### 1. Should the description say what the skill *does*?

- **skill-creator:** "description: When to trigger, **what it does**… include both
  what the skill does AND specific contexts for when to use it."
- **writing-skills:** "**Description = When to Use, NOT What the Skill Does**…
  NEVER summarize the skill's process or workflow."

These read as opposites, but the examples show they are not. Every "bad" case in
writing-skills is a *step sequence* — "write test first, watch it fail, write
minimal code, refactor". Its reasoning is specific and empirical: an agent that
can read the workflow in the description may act on it and never open the skill.
It reports a real case where a description mentioning "code review between tasks"
caused one review instead of the two the skill specified.

A one-line statement of purpose is not a workflow summary, and skill-creator is
right that a bare trigger list leaves the model unable to judge relevance.

**Resolved:** `description-recites-workflow` fires only on step *sequences*
(`first…then`, `then…then`, `1. … 2.`, arrow chains, "Step 1"). Stating purpose is
not flagged. Neither source's stronger claim is enforced.

### 2. Is "Use when you…" acceptable?

- **writing-skills:** "Start with `Use when…`" ✅
- **skill-development:** lists `description: Use this skill when you want to…` as
  **incorrect**, because it is second person.

The disagreement is only about the pronoun, not the opener. `Use when the user
asks…` satisfies both.

**Resolved:** the opener is never flagged. `description-second-person` fires on
the pronoun alone, at `info` — the lowest level, because the practical cost is
small and the published disagreement is real.

## Rule provenance

| Rule id | Level | Source | The guidance |
|---|---|---|---|
| `frontmatter-invalid` | error | all three | "SKILL.md file exists with valid YAML frontmatter" (skill-development validation checklist) |
| `name-missing` · `description-missing` | error | all three | "Frontmatter has `name` and `description` fields" |
| `name-mismatch` | error | skill-development | Plugin skills are discovered by directory; the frontmatter name must agree |
| `name-format` | warn | writing-skills | "Descriptive Naming — use active voice, verb-first"; every published skill is kebab-case |
| `description-vague` | warn | skill-development | Mistake 1, Weak Trigger Description: "Vague, no specific trigger phrases" |
| `description-no-trigger` | warn | skill-creator, writing-skills | "All 'when to use' info goes here"; "Start with 'Use when…'". skill-creator adds that Claude *undertriggers* skills, so descriptions should be "a little bit pushy" |
| `description-no-phrases` | info | skill-development | "Includes specific trigger phrases users would say"; "Lists concrete scenarios" |
| `description-first-person` | warn | writing-skills, skill-development | "Write in third person (injected into system prompt)"; "❌ BAD: First person" |
| `description-second-person` | info | skill-development | "The frontmatter description must use third person" — see conflict 2 |
| `description-recites-workflow` | warn | writing-skills | "NEVER summarize the skill's process or workflow" — see conflict 1 |
| `body-thin` | warn | skill-development | "Markdown body is present and substantial" |
| `body-too-long` | warn | skill-creator | "Keep SKILL.md under 500 lines; if you're approaching this limit, add an additional layer of hierarchy" |
| `body-too-many-words` | warn | skill-development | "Body is focused and lean (1,500–2,000 words ideal, <5k max)" |
| `trigger-info-in-body` | warn | skill-creator | "All 'when to use' info goes here, not in the body" |
| `shouty-directives` | info | skill-creator | "If you find yourself writing ALWAYS or NEVER in all caps… that's a yellow flag — if possible, reframe and explain the reasoning" |
| `force-loading-link` | warn | writing-skills | "❌ Bad: `@skills/…` (force-loads, burns context)… consuming 200k+ context before you need them" |
| `broken-reference` | warn | skill-development | "Referenced files actually exist"; "Mistake 4: Missing Resource References" |
| `reference-no-toc` | info | skill-creator | "For large reference files (>300 lines), include a table of contents" |

## Guidance deliberately not enforced

Some published guidance is real but not mechanically checkable, or is checkable
only with an unacceptable false-positive rate. Recording the omissions matters as
much as recording the rules — otherwise each gets rediscovered and re-argued.

| Guidance | Why it is not a rule |
|---|---|
| "Write in imperative form" (skill-development) | Detecting second person in a body needs to distinguish `you should configure X` from a quoted user phrase or a deliberate example. Early trials flagged good writing often enough to be noise. Better judged by a reader. |
| "Keyword coverage — error messages, symptoms, synonyms" (writing-skills) | Requires knowing the skill's domain. No pattern separates thorough coverage from padding. |
| Word-count targets: <150 for getting-started, <200 for frequently-loaded (writing-skills) | Depends on load frequency, which the file cannot know. `body-too-long` covers the outer bound that applies to everything. |
| "Examples are complete and working" (skill-development) | Needs execution, which is the eval loop's job. |
| Trigger accuracy | This is the one that actually matters, and only `skill-creator`'s optimiser measures it — by running 20 queries against the real model. No static check substitutes; the linter can verify a description *has* triggers, never that they *work*. |

That last row is the honest limit of this tool. A clean lint says nothing
mechanical is wrong. It does not say the skill fires, and it does not say the
skill is any good.
