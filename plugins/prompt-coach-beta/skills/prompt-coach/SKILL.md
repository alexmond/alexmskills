---
name: prompt-coach
description: A hook-driven coach that watches your prompts to Claude Code and nudges you toward proven prompting best practices (definition-of-done, scoped references, guardrails, verification). Ships a tiered rule catalog; rules quietly graduate once you consistently apply them so the coach fades as you improve. Beta.
---

# prompt-coach (beta)

## Quick start (v0.25+)

### 60-second setup

```
/plugin marketplace add alexmond/alexmskills
/plugin install prompt-coach-beta@alexmskills
/reload-plugins
```

Restart the session so the `UserPromptSubmit` hook registers. Then just prompt Claude normally — the coach analyzes every prompt in the background and nudges when a rule matches.

### What you'll see when a rule fires

A box appears above Claude's response with the rule id and a coaching hint:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 prompt-coach — vague-reference: Vague reference

The 'it/this/that' is doing a lot of work in that sentence. Which
file / PR / error are you pointing at?

Progress: 0/15 clean prompts → mastered
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

The nudge is a suggestion, not a block — Claude answers your prompt normally after it. Rules graduate to "mastered" after `graduation_threshold` clean prompts in a row (default 15), then the next dormant rule activates in its place.

### The 4 slash commands

| Command | When to use |
|---|---|
| `/prompt-coach-beta:stats` | *"How am I doing?"* Health dashboard: prompts analyzed, emit rate, top-fired rules, mastery status. |
| `/prompt-coach-beta:config` | *"Change my settings."* Verbs: `show`, `set`, `describe`, `options`, `mastery`, `sources`, `diff`, `export`, `reset`. |
| `/prompt-coach-beta:help` | *"What are my options?"* Compact live-config card + command list + say-it cheatsheet. |
| `/prompt-coach-beta:report-issue` | *"The coach was wrong."* Files a redacted GitHub issue (first-5-words + structural signature only). |

### Say-it phrases (natural language)

Claude edits your config file when you say any of these:

**Modes** — where the nudge appears:
- *"set prompt-coach to inline"* — nudge is rendered as the opening block of Claude's response (best for TUIs that don't show stderr)
- *"set prompt-coach to silent"* — Claude sees the nudge context, you don't
- *"set prompt-coach to log-only"* — every fire logged, nothing shown
- *"set prompt-coach to both"* — default: stderr box + Claude sees it

**Voice** — how nudges are phrased:
- *"set prompt-coach voice to plain"* — simple English, short sentences, no idioms (non-native friendly)
- *"set prompt-coach voice to colleague"* — default: direct, ends on a question

**Pause / disable:**
- *"coach pause 10"* — silence nudges for the next 10 prompts
- *"coach off <rule-id>"* — permanently disable one rule
- *"coach on <rule-id>"* — re-enable it

**Bug reporting:**
- *"coach that was wrong"* — flag the PRIOR prompt for `/report-issue`

### First-day tweaks

If English is a second language:
```
"set prompt-coach voice to plain"
```

If you want nudges rendered inline in Claude's response (not stderr box):
```
"set prompt-coach to inline"
```

If you're being nudged too often:
```
"show me prompt-coach mastery"        (dashboard of practicing vs mastered rules)
"coach off <rule-that-keeps-firing>"  (permanent silence per rule)
"coach pause 10"                      (silence everything for 10 prompts)
```

### Companion skill: log-review

For cross-repo analytics of coach activity, say **"log review"** or **"daily review"**. That invokes the standalone `log-review` skill at `~/.claude/skills/log-review/` (redacted-by-default output, safe to paste anywhere).

---

## How it works

A `UserPromptSubmit` hook analyzes every prompt you send Claude Code, matches it against a small
catalog of prompting-best-practice rules, and — at most once per prompt, with per-rule cooldowns —
emits a short nudge. Rules graduate to "mastered" after `graduation_threshold` clean prompts in a
row, at which point the next dormant rule activates. The coach fades as your prompts improve.

## What it watches for

**Six tiers** of ~5 rules each. Only 6 rules are active at once (`max_active_rules`,
default 6 as of v0.12) — lower tiers dominate; as an L1 rule masters, an L2 rule
activates in its place, and so on.

**L1 — fundamentals**
| Rule | Catches |
|---|---|
| vague-reference | "Fix it" / "improve this" with no named file/function |
| no-definition-of-done | Action verb with no acceptance criteria |
| unbounded-scope | "all / every / entire X" attached to a mutating verb |
| improve-without-metric | "better / faster / cleaner" with no measurable target |
| missing-guardrails | Heavy verb (refactor/rewrite/migrate) with no "don't touch X" |
| no-answer-shape | "What are X" / "how much of Y" question without a format spec (elevated L2→L1 in v0.12) |

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

## Conversational short-circuit (v0.6+)

Many prompts in an ongoing conversation aren't full asks — they're **approvals**
(`sure`, `publish`, `go`, `ship it`), **multi-choice picks** (`1 and 2`, `a and b`,
`option a`), or **continuations** (`continue`, `next`, `thanks`). The coach's rules
would misfire on these, and the typo normalizer would over-correct short conversational
words (e.g. `publish` → `polish` at edit distance 2).

`is_conversational()` catches these and short-circuits the analysis: no rule matching,
no typo correction, no praise, no streak updates. The prompt is still logged (with
`outcome: skipped:conversational`) so you can audit what was skipped. If a rule ever
needs to fire on this class of prompt, log inspection tells you to widen the trigger.

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
- `praise_ratio` — 1 praise per N clean prompts with a positive detection (default: 10, Kohn's don't-dilute threshold)
- `praise_on_mastery` — celebrate when a rule graduates (default: true)
- `praise_on_first_after_fire` — celebrate immediate corrections (default: true)
- `disable_praise` — silence all encouragement but keep nudges (default: false)
- `mastered_cooldown_prompts` — cooldown between refresher fires on mastered rules (default: 50; `0` disables refresher firing)
- `demote_on_regression` — object `{enabled, threshold, window}`; off by default. When on, auto-demotes a mastered rule that fires threshold+ times within window prompts.
- `typo_tolerance` — Levenshtein edit distance for typo normalization (default: 2, `0` disables)
- `llm_fallback.enabled` — stub for v0.6 opt-in LLM classification when regex misses (default: false)

Full source citations behind each rule: [`docs/sources.md`](../../docs/sources.md).

## nudge_style — four options (v0.10+)

| Style | User sees | Claude sees | When to use |
|---|---|---|---|
| `both` (default) | boxed nudge on **stderr** (dim area under prompt) | `additionalContext` with guidance | You want the nudge visible AND Claude to factor it in |
| `silent` | nothing | `additionalContext` with guidance | You've internalized the rules; just want Claude to compensate |
| `log-only` | nothing | nothing | Weekly review discipline — read `log.md`, no live nudges |
| **`inline`** (v0.10+) | **the boxed nudge is rendered as the opening block of Claude's response** | render instruction + guidance | You want the nudge **inline in your transcript**. Best if your TUI doesn't render hook stderr. |

### Switching modes

Just say it and Claude will edit the right file:

- *"Set prompt-coach to inline"* → writes `nudge_style: "inline"` to `~/.claude/prompt-coach/config.json`
- *"Set prompt-coach to silent"*
- *"Set prompt-coach to log-only for this repo"*
- *"Reset prompt-coach mode"* → deletes the local override so the global default takes over
- *"Disable praise"* → sets `disable_praise: true`
- *"Praise every N prompts"* → sets `praise_ratio: N`

### About inline mode

The mechanism: the hook writes an instruction into `additionalContext` telling Claude to render the
nudge box *verbatim* at the very start of its response, then continue with the actual task. Costs
~50 extra output tokens per fire and adds the nudge as a persistent line in your transcript. If a
nudge doesn't substantively apply because prior context resolves the ambiguity, Claude renders the
block but adds a one-line "(context resolves the ambiguity, proceeding)" note.

## Voice presets & sources (v0.17+)

Two orthogonal config knobs shape *how* the coach talks to you.

### `voice_preset` — personality

Chooses which set of pre-written phrasings the coach draws from.

- `colleague` (default) — friendly, direct, ends on a concrete question. Assumes fluent
  colloquial English and light idiom. "You said 'fix it' — what's 'it'?"
- `plain` — simple English, short sentences, no idioms, no jargon. Written for
  non-native speakers or anyone who prefers explicit phrasing. "Please tell me what
  'it' or 'this' is. For example: a file name, a PR number, or an error message."

Coverage: L1 + L2 rules (10 rules) ship both presets with 3 variants each = 60
phrasings. L3–L6 rules currently ship `colleague` only; if you pick `plain`, they
fall back to `colleague` (no crash, no missing text). L3–L6 `plain` variants will be
added as evidence surfaces which rules fire most.

Switch it conversationally:

- *"set prompt-coach voice to plain"*
- *"set prompt-coach voice to colleague"*
- *"reset prompt-coach voice"*

### `voice_source` — who authors the sentence

Independent of preset. Chooses whether the nudge text is drawn from the static
catalog or composed fresh by Claude.

| Source | How | Cost per fire | Determinism |
|---|---|---|---|
| `static` (default) | Pre-written variants from the catalog. Rotates + follows disclosure levels. | 0 tokens, ~0 ms | Deterministic — same rule, same context → same text (mod novelty rotation) |
| `llm-compose` | Hook passes rule id + guidance + your prompt shape to Claude in `additionalContext`; Claude writes the nudge fresh, primed to reflect *this specific* prompt with 6 anti-disagreement guardrails. | +200–800 ms, ~150–400 output tokens per fire | Non-deterministic; may feel repetitive-in-a-different-way |
| `hybrid` | First fire in the window = static preset (deterministic, teaching-focused). Medium/short refreshers = llm-compose (livelier when you've already learned the rule and want a light-touch reminder). | Costs both, sparingly | Mixed |

Anti-disagreement guardrails baked into `llm-compose`: must open with the rule id
header verbatim, must not override the rule even if context resolves the referent,
must end on a concrete ask, word-count cap by disclosure level, must match the
preset's voice.

The `outcome` log line now records preset + source per fire (e.g.
`nudged:inline:full:v1:p=plain:src=static`) so `/prompt-coach-beta:stats` can
mine which combination you actually converge on.

## Cross-repo daily review — moved out (v0.23+)

The v0.21-v0.22 `/prompt-coach-beta:daily-review` command was extracted
to a standalone user skill at `~/.claude/skills/log-review/`. Rationale:
its output (repo names, per-repo activity) shouldn't be produced by the
coach; keeping it separate means the coach never generates content that
could leak repo topology when pasted into a GitHub artifact.

Invoke by saying *"log review"* / *"daily review"* / *"what's new"* — Claude
picks up the skill from `~/.claude/skills/log-review/`. Redacted-by-default
(`repo-1`, `repo-2`, …); `--show-repos` for local inspection. Watermark for
"since last review" semantics. Data source is unchanged: it reads the same
`.claude/prompt-coach/log.md` files the coach writes.

## Options + interactive flows + mastery (v0.19+)

Three additions on top of v0.18's `:config`:

- `+/prompt-coach-beta:config options <key>+` — enumerates legal values for a key
  with per-choice explanations. For enums like `voice_source`, lists each choice
  and what it does. For int/bool/list, shows current + default + example +
  description. Answers *"what modes exist?"* without needing to already know.
- `+/prompt-coach-beta:config quick+` — interactive multi-choice picker for the
  ~4 categorical settings (`voice_preset`, `voice_source`, `nudge_style`,
  `praise_ratio`). Claude walks you through with AskUserQuestion; each answer
  routes to `:config set`.
- `+/prompt-coach-beta:config full+` — same pattern for every schema key. Enum
  keys → picker; numeric/bool → "keep current / type new value / reset to
  default". Longer flow; you can skip categories.
- `+/prompt-coach-beta:config mastery+` — dashboard of rule states: *mastered*
  (with mastery date), *in-progress* (fires_total > 0, streak/threshold),
  *dormant* count by tier. Answers *"how am I doing?"*.
- `+/prompt-coach-beta:config mastery-reset <rule-id>+` — resets one rule's
  fires/streak/status/mastered_at (dry-run first).
- `+/prompt-coach-beta:config mastery-reset-all+` — wipes all rule state
  (preserves `prompt_count` and non-rule state; dry-run first).

Under the hood, enum keys now carry `choice_descriptions` in `CONFIG_SCHEMA` —
same forward-compat pattern as v0.18. Adding a new enum config means adding a
`choice_descriptions` dict; `options` picks it up automatically.

## Config surface (v0.18+)

The coach's config has grown to 22 keys across 8 categories. `/prompt-coach-beta:config`
is the structured surface — it reads a `CONFIG_SCHEMA` metadata dict alongside
`DEFAULT_CONFIG`, so future options are picked up automatically once they land in the
schema.

```
/prompt-coach-beta:config                         categorized dashboard
/prompt-coach-beta:config show <category>         one category only
/prompt-coach-beta:config get <key>               resolved value
/prompt-coach-beta:config describe <key>          type, default, choices, since
/prompt-coach-beta:config set <key> <value>       validate + write
/prompt-coach-beta:config reset <key>             remove your override
/prompt-coach-beta:config reset-all               wipe scoped config (confirm!)
/prompt-coach-beta:config diff                    only what you've changed
/prompt-coach-beta:config export                  resolved config as JSON
```

Flags: `--scope global|repo` (default `global`), `--dry-run` (on set/reset), `--json`
(machine-readable).

**Categories**: `output`, `voice`, `rule-activation`, `mastery`, `praise`,
`typo-tolerance`, `anti-habituation`, `llm-fallback`.

**Say-it phrases still work** — you can keep saying *"set prompt-coach to inline"*,
*"coach off no-few-shot"*, etc. Claude routes those to `:config set` under the hood.
The command is the discoverable path when you don't know what the options are called.

Writes are deep-merged into the target JSON — keys the schema doesn't know about
(e.g. forward-compat entries from future versions) are preserved, not stripped.
Invalid values (wrong type, not in `choices`) are rejected with a clear error.

## Anti-habituation (v0.16+)

Same message repeated wears out. The literature (Hattie & Timperley 2007 on feedback wear-out;
Sasse & Rashid 2013 on alert fatigue; ad-tech creative-wearout research) converges on **variety
+ frequency capping + escalation** as the combination that keeps coaching salient. The coach
ships all four:

- **Variant pool** — L1 rules have 3 phrasing variants each, hand-written in a "colleague giving
  quick feedback" voice. Rotates on each fire.
- **Novelty constraint** — never repeats a variant within the last 2 fires of the same rule.
- **Progressive disclosure** — fires_in_window drives format: full box for the first fire,
  medium box (no sources, no progress line) for the 2nd–3rd, one-liner for the 4th+.
- **Silence after saturation** — 5 fires within 30 prompts triggers a 30-prompt silence on
  that rule. Absence is a signal: coaching isn't landing, going quiet is more honest than
  nagging.

Config knobs: `saturation_threshold` (default 5), `silence_window` (30), `silence_duration`
(30), `disclosure_medium_at` (2 fires in window), `disclosure_short_at` (4).

## Mastery ≠ silence (v0.9+)

Mastered rules aren't permanently dormant — they still evaluate every prompt, just emit rarely.
When only a mastered rule matches (no practicing rule fired), you get a **refresher**: a
one-line softer box (`🔄 prompt-coach — refresher on <rule>`) rather than the full nudge.

Cooldown for practicing rules: 5 prompts. **Cooldown for mastered rules: 50 prompts** (10×
longer). Set `mastered_cooldown_prompts: 0` in config to disable refresher firing entirely
(reverts to permanent-silence-on-mastery behavior).

**Priority when both fire in the same prompt**: nudge (practicing) > refresher (mastered) >
praise. Nothing dilutes anything.

**Optional self-healing** (`demote_on_regression: {enabled: false, threshold: 3, window: 30}`):
if a mastered rule fires 3+ times within 30 prompts, demote it back to practicing. Off by
default — being surprised by a graduated rule reactivating is unpleasant. Users who want strict
self-healing turn this on.

## Introspection — `/prompt-coach-beta:stats`

Type `/prompt-coach-beta:stats` (v0.8+) to see a compact dashboard: total prompts analyzed,
nudge/praise/skipped counts, emit rate, most-fired rules, mastered rules, top typo corrections,
and current config. Answers "is this thing actually doing anything?" without opening files.

Read-only; the command never modifies state.

## Reporting bad calls (v0.13+)

If the coach mistreated a prompt (false positive, false negative, wrong rule, bad wording),
mark it on the **very next turn** with any of these phrases:

- *"coach that was wrong"*
- *"coach missed this"*
- *"coach false positive"*
- *"bad nudge"* / *"wrong nudge"*
- *"coach mistreated my prompt"*

The analyzer flags the PRIOR substantive prompt's analysis (not the current complaint) into
`.claude/prompt-coach/candidates.jsonl`. Later, run:

```
/prompt-coach-beta:report-issue
```

The command reads the queue, computes a structural signature (word count, verb-shape,
has-file-ref, is-question, etc.), redacts to the **first 5 words** of the prompt only, asks
you for a one-line annotation per case, shows a full preview, and only then files a
`gh issue create` to `alexmond/alexmskills` with label `prompt-coach` — after you confirm.

**Privacy guarantees**: only first-5-words + structural booleans + your annotation get filed.
Full prompts stay in `log.md` locally. You see the exact payload before it's posted.

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

## Verify it's on

- New prompt should either produce a boxed nudge on stderr (when `nudge_style: both` and a rule
  fires), an inline block at the start of Claude's response (when `nudge_style: inline`), or
  leave `.claude/prompt-coach/log.md` growing (all modes).
- Global counter: `jq '.prompt_count' ~/.claude/prompt-coach/state.json` should increment per
  prompt.
- If neither happens, the hook may not be registered — check `enabledPlugins` in
  `.claude/settings.json` for `prompt-coach-beta@alexmskills`.

## Future — Java MCP server

The current Python + `UserPromptSubmit` hook is CLI-only. A Java MCP
server is planned so the coach can run in claude.ai chat, aggregate
telemetry across users, and support persistent per-user state. Living
spec: [`docs/java-mcp-spec.md`](../../docs/java-mcp-spec.md) — updated
on every minor version bump. It captures the target architecture, MCP
surface, canonical rule catalog format, data model, privacy model, and
migration path from the current Python plugin.

The prerequisite for building the server is **training data from real
users at scale**, not a single maintainer's log. The
`/prompt-coach-beta:report-issue` command already produces
training-data-shaped payloads (structural signature + first-5-words +
user annotation) — that's the collection mechanism the future server
will consume.

## Design notes

- **Pure heuristics.** Rules are regex + short-window checks; no LLM call per prompt. Cheap,
  deterministic, ~10 ms.
- **False positives are OK.** Cooldowns prevent pestering; graduation rewards you for consistent
  clean prompts even in the face of an over-eager rule.
- **Sources are diverse.** Each rule cites 2–3 outside-of-Anthropic and inside-Anthropic sources
  so the catalog isn't opinion-of-one.
- **Beta.** Local until it earns its stable slot. Graduation criteria for the plugin itself: two
  weeks of nightly use across ≥2 repos + at least one rule graduated to mastered per repo.
