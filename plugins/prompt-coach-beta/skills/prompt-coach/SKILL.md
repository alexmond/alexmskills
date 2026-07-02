---
name: prompt-coach
description: A hook-driven coach that watches your prompts to Claude Code and nudges you toward proven prompting best practices (definition-of-done, scoped references, guardrails, verification). Ships a tiered rule catalog; rules quietly graduate once you consistently apply them so the coach fades as you improve. Beta.
---

# prompt-coach (beta)

A `UserPromptSubmit` hook analyzes every prompt you send Claude Code, matches it against a small
catalog of prompting-best-practice rules, and — at most once per prompt, with per-rule cooldowns —
emits a short nudge. Rules graduate to "mastered" after `graduation_threshold` clean prompts in a
row, at which point the next dormant rule activates. The coach fades as your prompts improve.

## What it watches for

Five tiers of ~5 rules each. Only 5 rules are active at once (`max_active_rules`) —
lower tiers dominate; as an L1 rule masters, an L2 rule activates in its place, and so on.

**L1 — fundamentals**
| Rule | Catches |
|---|---|
| vague-reference | "Fix it" / "improve this" with no named file/function |
| no-definition-of-done | Action verb with no acceptance criteria |
| unbounded-scope | "all / every / entire X" attached to a mutating verb |
| improve-without-metric | "better / faster / cleaner" with no measurable target |
| missing-guardrails | Heavy verb (refactor/rewrite/migrate) with no "don't touch X" |

**L2 — intermediate**
| Rule | Catches |
|---|---|
| compound-tasks | Three+ action verbs joined by "and" |
| no-verify-loop | Implementation ask with no verification step |
| missing-context-fetch | "The failing test / the issue" with no identifier |
| no-format-spec | Ask for summary/list/report with no shape |

**L3 — classical prompting techniques**
| Rule | Catches |
|---|---|
| no-adversarial-check | High-stakes ask (security/migration/prod/delete) with no skeptic |
| retry-without-diagnosis | Short "try again" with no new information |
| no-few-shot | "Like X" / "in the style of Y" without an example |
| no-chain-of-thought | Reasoning ask (why/debug/trace) without "think first" |
| no-rubric | Judgment ask ("is this good?") without criteria/axes |
| no-uncertainty-budget | Investigative ask with no "if unsure, say so" |

**L4 — goals & loops**
| Rule | Catches |
|---|---|
| implicit-goal | Action prompt with no "so that / in order to / why" clause |
| unbounded-iteration | "Keep improving" without a stopping condition |
| no-rubric-for-refine | "Refine this" without naming which axis to improve |

**L5 — Claude-Code tool-native**
| Rule | Catches |
|---|---|
| no-plan-mode-for-risky | Migration / delete / rewrite ask with no "plan first" |
| no-task-list-for-multi-step | 3+ action verbs without a TaskCreate / checklist ask |
| no-agents-for-parallel-lookup | Multiple independent lookups without parallel agents |
| no-role-for-critique | "Review my X" without invoking a role (skeptic / security / reviewer) |
| no-panel-for-contested-design | "Which is better / torn between" without brainstorm-panel |
| no-workflow-for-fanout | "For each of these 20+ things" without Workflow / parallel agents |

**L6 — skill-awareness**
| Rule | Catches |
|---|---|
| no-skill-lookup | "How do I X" / "what's the standard way" without checking existing skills |
| pattern-worth-abstracting | "Again / same as before / yet another" — rule of three, worth a skill? |
| no-skill-composition | Multi-step repeatable ceremony not named as a skill candidate |

## Encouragement layer (v0.3+)

The coach also *praises the specific positive behaviors* mirroring the negative rules — 21 detectors,
sparing (default 1-in-10 clean prompts + always on mastery + always on first-after-fire), and
grounded in behavioral-science literature (Brophy 1981, Mueller & Dweck 1998, Fogg 2019, Deci & Ryan
2000, Kohn 1993). Design choices:

- **Never on a nudged prompt** — praise + correction on the same prompt dilutes both (Kohn).
- **Specific, not generic** — describes what you did (`"you attached a metric to 'better'"`) rather
  than evaluating you (`"great prompt"`).
- **Process, not trait** (Dweck) — praises the *technique*, not you.
- **Variable-ratio** (Skinner) — intermittent praise stays potent; every-time praise becomes noise.
- **Rotated phrasings** — 2–3 per rule, plus a light touch of warmth/humor.
- **Milestone events** — a rule graduating to *mastered* and a "first-after-fire" (you did the
  thing you were nudged on last prompt) are always recognized regardless of ratio.

## Typo tolerance (v0.5+)

A pre-pass normalizes each prompt against a curated set of ~90 trigger words drawn from the rule
catalog — dyslexic-friendly, transposition-friendly, deterministic, and zero-dependency (banded
Levenshtein, ~1 ms). Corrections are made only when:

- The token is ≥ 5 chars, all-alphabetic, and NOT already a trigger word.
- Its closest trigger word is **uniquely** the closest (ties = no correction, so `text` doesn't
  become `test`).
- Adaptive tolerance: distance-1 for tokens ≤ 6 chars, distance-2 for longer (kills the
  "public ↔ rubric" class of collision, keeps "refacotr ↔ refactor").

Examples that get corrected: `refacotr` → `refactor`, `evrything` → `everything`,
`veryfy` → `verify`, `cleanre` → `cleaner`, `migrat` → `migrate`. Every correction is logged.

**Fallback count is a self-report signal.** Rising `normalization_stats.tokens_corrected_total` /
`prompts_with_corrections` (in `~/.claude/prompt-coach/state.json`) says the rule regexes aren't
covering your real prompts and it's worth tuning. Once the LLM fallback (v0.6, opt-in) ships,
`llm_fallback_stats.calls_total` gives the same signal one level up. Ask *"show me prompt-coach
stats"* and Claude will summarize.

Set `typo_tolerance: 0` in config to disable the normalization pass entirely.

## Configuration

Config resolves in order: repo local → user global → default. Keys:

- `nudge_style` — `"both"` (default) / `"silent"` / `"log-only"`. Applies to praise as well.
- `graduation_threshold` — clean prompts in a row → mastered (default: 15)
- `cooldown_prompts` — min prompts between same-rule nudges (default: 5)
- `max_active_rules` — never nag on more than this many rules at once (default: 5)
- `pause_until_prompt` — skip nudging until global `prompt_count` passes this
- `disabled_rules` — array of rule ids to permanently silence
- `praise_ratio` — 1 praise per N clean prompts (default: 10)
- `praise_on_mastery` — celebrate when a rule graduates (default: true)
- `praise_on_first_after_fire` — celebrate immediate corrections (default: true)
- `disable_praise` — silence all encouragement but keep nudges (default: false)
- `typo_tolerance` — Levenshtein edit distance for typo normalization (default: 2, `0` disables)
- `llm_fallback.enabled` — stub for v0.6 opt-in LLM classification when regex misses (default: false)

Full source citations behind each rule: [`docs/sources.md`](../../docs/sources.md).

## How to switch modes

Just say it and Claude will edit the right file:

- *"Set prompt-coach to silent"* → writes `nudge_style: "silent"` to `~/.claude/prompt-coach/config.json`
- *"Set prompt-coach to log-only for this repo"* → writes `nudge_style: "log-only"` to `.claude/prompt-coach/config.json`
- *"Reset prompt-coach mode"* → deletes the local override so the global default takes over
- *"Disable praise"* → sets `disable_praise: true`
- *"Praise every N prompts"* → sets `praise_ratio: N`

## Pause / disable (say-it phrases)

- *"Coach pause 10"* — silence nudges for the next 10 prompts. Claude sets `pause_until_prompt` in
  global state.
- *"Coach off vague-reference"* — permanently disable a single rule. Claude appends the id to
  `disabled_rules` in `~/.claude/prompt-coach/config.json`.
- *"Coach on vague-reference"* — remove from `disabled_rules`.
- *"Coach reactivate no-definition-of-done here"* — re-open a rule that graduated globally, just
  for this repo. Claude adds the id to `reactivated` in `.claude/prompt-coach/state.json`.

## State layout

```
~/.claude/prompt-coach/
├── config.json        # global config (nudge_style, thresholds, disabled_rules)
└── state.json         # global mastery ledger: fires_total, clean_streak, status per rule

<repo>/.claude/prompt-coach/
├── config.json        # per-repo overrides (nudge_style, disabled_rules)
├── state.json         # per-repo fires_here, reactivations
└── log.md             # rolling log of nudges + prompt previews
```

Config keys (all optional; defaults in [`scripts/analyze-prompt.py`](../../scripts/analyze-prompt.py)):

- `nudge_style` — `"both" | "silent" | "log-only"`
- `graduation_threshold` — clean prompts in a row → mastered (default: 15)
- `cooldown_prompts` — minimum prompts between same-rule nudges (default: 5)
- `max_active_rules` — cap on how many rules can nag at once (default: 5)
- `pause_until_prompt` — skip nudging until global `prompt_count` passes this
- `disabled_rules` — array of rule ids to permanently silence

## Verify it's on

- New prompt should either produce a boxed nudge on stderr (when `nudge_style: both` and a rule
  fires) or leave `.claude/prompt-coach/log.md` growing.
- Global counter: `jq '.prompt_count' ~/.claude/prompt-coach/state.json` should increment per
  prompt.
- If neither happens, the hook may not be registered — check `enabledPlugins` in
  `.claude/settings.json` for `prompt-coach@alexmskills-beta`.

## Design notes

- **Pure heuristics.** Rules are regex + short-window checks; no LLM call per prompt. Cheap,
  deterministic, ~10 ms.
- **False positives are OK.** Cooldowns prevent pestering; graduation rewards you for consistent
  clean prompts even in the face of an over-eager rule.
- **Sources are diverse.** Each rule cites 2–3 outside-of-Anthropic and inside-Anthropic sources
  so the catalog isn't opinion-of-one.
- **Beta.** Local until it earns its stable slot. Graduation criteria for the plugin itself: two
  weeks of nightly use across ≥2 repos + at least one rule graduated to mastered per repo.
