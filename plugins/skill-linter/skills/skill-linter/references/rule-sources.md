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

### Added in 0.3.0 (deep-research sweep, 2026-08-18)

| Short name | What it is |
|---|---|
| **platform-bp** | [Skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) — the official page with the hard numbers: name/description caps, 500-line body, one-level references, TOC guidance, anti-pattern list. |
| **agentskills-spec** | [agentskills.io/specification](https://agentskills.io/specification) — the Agent Skills spec: name grammar, 1024-char description, the six portable frontmatter fields, <5k-token body. |
| **code-skills** | [code.claude.com/docs/en/skills](https://code.claude.com/docs/en/skills) — Claude Code specifics: the 1,536-char listing truncation, empty-metadata-on-bad-YAML, the claude.ai hard-fail on non-spec fields. |
| **anthropic-eng** | [Equipping agents for the real world](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) — run-vs-read intent for bundled scripts. |
| **fsck** | Jesse Vincent, [Skills not triggering](https://blog.fsck.com/2025/12/17/claude-code-skills-not-triggering/) — the shared ~15,000-char description budget across all installed skills. |
| **willison** | [Simon Willison on Claude Skills](https://simonwillison.net/2025/Oct/16/claude-skills/) — frontmatter as the only always-loaded cost. |
| **cursor / copilot / codex** | [Cursor rules](https://cursor.com/docs/context/rules) (500-line cap), [Copilot custom instructions](https://docs.github.com/en/copilot/tutorials/customize-code-review) (~1,000-line decay, vague-exhortation list), [OpenAI Codex best practices](https://developers.openai.com/codex/learn/best-practices) — cross-vendor corroboration, never primary. |

All three original sources agree on the fundamentals: `name` + `description` frontmatter, the
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

### 3. When does a reference file need a table of contents?

- **platform-bp:** files over **100 lines** should include a TOC.
- **skill-creator:** "For large reference files (>**300 lines**), include a table of contents."

Both official, both current, 3× apart. On the 69-skill calibration corpus the
100-line threshold would flag many well-regarded skills; the 300-line one flags
six. **Resolved:** `reference-no-toc` stays at 300 lines, info-level. The
stricter 100-line guidance is real and is recorded here so it isn't
rediscovered — revisit if partial-read failures show up in practice.

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

### Spec-limit and budget rules (0.3.0)

Added after a verified deep-research sweep (87 claims from 6 source categories,
41 surviving adversarial verification; full record in
`docs/decisions/2026-08-18-skill-authoring-research.md`). Calibration: the full
set adds **+20 warnings across 69 external skills**, every one hand-verified as
a true positive, and **zero new findings** on this repo's already-clean skills.

| Rule id | Level | Source | The guidance |
|---|---|---|---|
| `name-spec` | warn | agentskills-spec, platform-bp | "1-64 chars, lowercase alphanumerics and hyphens", no leading/trailing/consecutive hyphens; claude.ai upload rejects violations |
| `name-generic` | warn | platform-bp | The Avoid list, verbatim: `helper` `utils` `tools` `documents` `data` `files` — names that say nothing about when to trigger |
| `description-too-long` | warn | agentskills-spec, platform-bp | "Maximum 1,024 characters, non-empty" — a hard error on claude.ai, silent truncation in Code |
| `description-truncated` | warn | code-skills | "the combined `description` and `when_to_use` text is truncated at 1,536 characters in the skill listing" |
| `description-xml-tags` | warn | platform-bp | "no XML tags" in name or description. Narrowed to real markup (closing/self-closing/attributed tags) — bare `<placeholder>` tokens are CLI idiom and produced 5 FPs unnarrowed |
| `compatibility-too-long` | warn | code-skills, agentskills-spec | "Accepts a string of up to 500 characters" |
| `frontmatter-unknown-key` | warn | code-skills (hard-fail note), redesigned per calibration | A key in neither the spec's six nor Claude Code's documented extras is usually a typo, and a typo'd field is silently dropped. First cut flagged all non-spec keys — 14 hits on this repo's legitimate `argument-hint` uses — so it now warns only on keys *no* runtime documents |
| `body-far-too-long` | error | copilot (corroborates platform-bp, cursor) | "Limit any single instruction file to a maximum of about 1,000 lines. Beyond this, the quality of responses may deteriorate" — the only vendor with a documented decay point, hence the error threshold |
| `body-token-budget` | warn | platform-bp overview, agentskills-spec | Level-2 progressive disclosure: "Under 5k tokens". Estimated as chars/4; complements the line check for long-line files |
| `vague-exhortation` | info | copilot, self.md | "Vague quality improvements … add noise without improving effectiveness"; state measurable constraints instead |
| `windows-path` | info | platform-bp | "always use forward slashes" — narrowed to drive-letter paths only, since a general backslash regex matches regex escapes everywhere |
| `reference-chain` | warn | platform-bp, superpowers/anthropic-best-practices | "Keep references one level deep from SKILL.md" — nested chains get partially read (`head -100`) and the tail is lost. Aggregated to one finding per skill: cloudflare's doc-tree produced 174 rows unaggregated |
| `script-unreferenced` | warn | anthropic-eng | Every bundled script needs its run-vs-read intent stated; a script SKILL.md never names is dead weight. Aggregated per skill |
| `collection-desc-budget` | warn | fsck | "the limit for skill and command descriptions defaults to 15,000 characters (or around 4000 tokens)" — skills past the cutoff silently never trigger. Fires once per multi-skill run |

The broadened trigger regex (added `load when`, `use this to`, `use for`,
`whenever` already present) traces to three independent verifier notes that the
old pattern rejected legitimate phrasings — an FP class in the linter's most
important rule.

### Agent rules (0.2.0)

| Rule id | Level | Source | The guidance |
|---|---|---|---|
| `agent-wrong-tools-field` | error | Claude Code subagent docs; miss on 2026-08-18 | Agent definitions restrict tools via `tools:`; `allowed-tools:` is the slash-command field and is silently ignored — the agent then runs with the full tool set. Graduated straight to shipped because the damage class is a false safety claim. |
| `agent-unknown-tool` | warn | same | A misspelled tool name grants nothing and fails silently at delegation time. |
| agent `name-mismatch` / `description-no-trigger` | error / warn | same reasoning as the skill rules | Delegation addresses agents by name and selects them by description. |

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

| Reserved words `anthropic`/`claude` in names (platform-bp) | Real spec rule, deliberately not enforced: it is a *publication* constraint for claude.ai, and half the Claude Code ecosystem legitimately ships `claude-*` names — this repo's own `evolving-claude-md` included. Flagging them locally is noise; recorded here so the rule isn't "discovered" and added later. |
| Gerund-form names (platform-bp "prefer gerunds") | A preference, not a requirement, and most good skills (including Anthropic's own `skill-creator`) don't follow it. The generic-name denylist covers the enforceable core. |
| Skills directory under version control (codemeetai) | True and useful, but a property of the machine, not the file — out of scope for a file linter. |

That last row is the honest limit of this tool. A clean lint says nothing
mechanical is wrong. It does not say the skill fires, and it does not say the
skill is any good.
