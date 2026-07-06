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

As of v0.34 the coach is a **collaborator** (not a nagger): when a rule fires, Claude reads your prompt in context and rewrites it with the fix baked in, at the top of its response:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💬 prompt-coach — I read your prompt as:

    "in src/auth/login.js, update handleLogin() to reject empty
     password submissions with a 422 and a 'password required'
     message. Keep the existing test suite green."

Changes:
  [1] Named the file + function (was: 'the login flow')
  [2] Made the behavior explicit + added a guardrail

Sources: https://…/be-clear-and-direct

Reply "yes" to proceed, "no" for original, or "edit" to change something.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

On a **clean** prompt you instead get a one-line `✓` heartbeat (v0.35). The coach is a suggestion, not a block — Claude answers your prompt normally. Rules graduate to "mastered" once you've **demonstrated** the good technique `min_demonstrations` times (default 3, v0.40 earned-mastery model), then the next dormant rule activates.

### The 5 slash commands

| Command | When to use |
|---|---|
| `/prompt-coach-beta:stats` | *"How am I doing?"* Health dashboard: prompts analyzed, emit rate, top-fired rules, mastery status. |
| `/prompt-coach-beta:mastery` | *"Which rules mastered, which need reset?"* Per-rule breakdown + analysis (well-tested / barely-tested / untested masteries; close-to-mastery). |
| `/prompt-coach-beta:config` | *"Change my settings."* Verbs: `show`, `set`, `describe`, `options`, `mastery`, `sources`, `diff`, `export`, `reset`. |
| `/prompt-coach-beta:help` | *"What are my options?"* Compact live-config card + command list + say-it cheatsheet. |
| `/prompt-coach-beta:report-issue` | *"The coach was wrong."* Files a redacted GitHub issue (first-5-words + structural signature only). |

### Say-it phrases (natural language)

Claude edits your config file when you say any of these:

**On/off** (v0.29+):
- *"disable prompt-coach"* / *"turn coach off"* — full silence in this scope (`enabled: false`)
- *"enable prompt-coach"* — turn it back on
- *"coach pause 10"* — temporary silence for 10 prompts

(Rendering is always inline. As of v0.38 the coach is collaborator-only — Claude
rewrites your prompt fresh each time — so the pre-v0.38 `nudge_style`,
`voice_preset`/`voice_source`, and anti-habituation options were all removed.)

**Analyze / docs / files** (v0.36+):
- *"analyze this prompt: <text>"* / *"analyze my last 20 prompts"* — full-catalog coaching on demand
- *"open the docs for <rule>"* — open the Anthropic guide section in a browser
- *"show me the skill folders"* — list the plugin's folders, state files, runnable scripts

**Pause / disable:**
- *"coach pause 10"* — silence nudges for the next 10 prompts
- *"coach off <rule-id>"* — permanently disable one rule
- *"coach on <rule-id>"* — re-enable it

**Bug reporting:**
- *"coach that was wrong"* — flag the PRIOR prompt for `/report-issue`

### First-day tweaks

To fully disable the coach in this repo/scope:
```
"disable prompt-coach"
```
(Coach is collaborator-only + inline as of v0.38 — no rendering mode or voice to pick.)

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
| incremental-routing | Multi-step task routed one terse step at a time ("continue" / "one after another" / "do the next one") instead of a batched task list / Workflow |

**L6 — skill-awareness**
| Rule | Catches |
|---|---|
| no-skill-lookup | "How do I X" / "what's the standard way" without checking existing skills |
| pattern-worth-abstracting | "Again / same as before / yet another" — rule of three, worth a skill? |
| no-skill-composition | Multi-step repeatable ceremony not named as a skill candidate |

## Encouragement layer (v0.3+)

The coach also *praises the specific positive behaviors* mirroring the negative rules — 35 detectors (one per rule),
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

> **v0.35 fix:** the praise layer had no inline-render branch, so from v0.29 (when rendering
> became inline-only) through v0.34 all of the above — including the mastery congrats — was
> computed then silently dropped. v0.35 restores it: mastery renders `🎓 prompt-coach — you
> mastered …`, first-after-fire and positives render `✨ prompt-coach — …`.

## Liveness acknowledgment (v0.35+)

The coach used to speak *only* on a rule hit, so a clean prompt produced silence and you
couldn't tell it was alive. `ack_clean` (default **on**) fixes that: on a clean prompt where
nothing else fired, it emits one compact ambient line —

```
✓ prompt-coach · clean prompt · closest to mastery: no-verify-loop 2/3 demonstrated
```

**This is not praise — it's a heartbeat.** The distinction is deliberate and grounded:

- **Informational, not evaluative.** Praise conveys a judgment ("good job") and must stay
  sparing or it wears out (Kohn 1993; Deci & Ryan 2000 on controlling vs *informational*
  feedback). A progress counter conveys competence *information* — like a test runner's green
  dot or a shell's git-branch segment — so it can be frequent without the wear-out.
- **Endowed-progress effect** (Nunes & Drèze 2006) — surfacing "N/threshold to mastery" makes
  the goal feel closer and pulls you toward it.
- **Status channel, not alert channel** (Sasse & Rashid 2013 on alert fatigue) — a distinct
  `✓` glyph (vs 🎯 nudge / 🔄 refresher / 💡 tip / ✨🎓 praise) reads as ambient status, not a
  demand for action.

**Priority ladder:** nudge/collaborator › refresher › praise › tip › ack. The ack fires only
when nothing else spoke, so the coach never stacks two messages on one prompt.

**Config:** `ack_clean` (bool, default true) · `ack_ratio` (int, default 1 = every clean prompt;
raise to 5/10 for a quieter pulse). Say *"turn off prompt-coach acks"* or *"coach ack every 10"*.

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

Config resolves in order: repo local → user global → default. Run
`/prompt-coach-beta:config show` for the live, schema-backed list. Key knobs:

- `enabled` — master switch; `false` = the hook returns immediately (default: true)
- `ack_clean` / `ack_ratio` — the `✓` liveness heartbeat on clean prompts + its rate (default: true / 1)
- `show_source_urls` — full clickable doc URLs in the coach block (default: true)
- `min_demonstrations` — **earned mastery (v0.40)**: times the mirroring positive must fire (you *used* the technique) before a rule can master (default: 3)
- `regression_guard` — clean prompts since the last fire required alongside the demonstrations (default: 3)
- `inactive_after` — clean_streak with zero demonstrations after which a rule retires *inactive* (default: 15)
- `graduation_threshold` — clean-streak recency/decay signal; no longer drives mastery since v0.40 (default: 15)
- `min_fires_for_mastery` — legacy v0.27 gate, superseded by `min_demonstrations`; retained but ignored
- `cooldown_prompts` — min prompts between same-rule fires (default: 5)
- `mastered_cooldown_prompts` — cooldown between refresher fires on mastered rules (default: 50; `0` disables)
- `max_active_rules` — cap on practicing rules active at once (default: 6)
- `pause_until_prompt` — skip until global `prompt_count` passes this
- `disabled_rules` — array of rule ids to permanently silence
- `praise_ratio` / `praise_on_mastery` / `praise_on_first_after_fire` / `disable_praise` — encouragement layer
- `tips_enabled` — proactive advanced-technique tips (default: true)
- `typo_tolerance` — Levenshtein edit distance for typo normalization (default: 2, `0` disables)

> **v0.38 removed** the legacy `nudge_style`, `voice_preset`/`voice_source`, and the
> anti-habituation keys (`saturation_threshold`, `silence_window`, `silence_duration`,
> `disclosure_medium_at`, `disclosure_short_at`) along with the hand-written nudge path.
> The coach is **collaborator-only**: when a rule fires Claude rewrites your prompt fresh,
> so there is no preset to pick and no repeated text to habituate to.

Full source citations behind each rule: [`docs/sources.md`](../../docs/sources.md).

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
  with per-choice explanations. For int/bool/list, shows current + default +
  example + description. Answers *"what modes exist?"* without needing to already know.
- `+/prompt-coach-beta:config quick+` — interactive multi-choice picker for the
  ~4 high-value settings (`ack_clean`, `show_source_urls`, `praise_ratio`, `tips_enabled`).
  Claude walks you through with AskUserQuestion; each answer routes to `:config set`.
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

## Earned mastery (v0.40+)

Mastery is driven by **demonstrations — times you actively *used* the good technique** (the
mirroring positive detector fired), not by the absence of the mistake. Before v0.40 a rule
graduated after a clean streak, but "clean" just meant the anti-pattern was absent — and since
most prompts don't exercise most rules, a rule could master on prompts unrelated to it.

Every rule now has a positive mirror (35/35). When a positive fires it's a demonstration:
`demonstrations` **drives mastery**, `clean_streak` is demoted to a recency guard, `fires_total`
is a regression signal. A rule masters when `demonstrations ≥ min_demonstrations` (default 3)
and it hasn't relapsed in the last `regression_guard` prompts. A rule neither demonstrated nor
tripped over a long window retires *inactive*. Existing masteries are **grandfathered** (tagged
`mastery_basis: legacy`); `mastery-reset <rule>` makes one re-earn it honestly.

## Adaptive coaching (v0.41+)

The coach learns which rules are worth firing *for you* by closing the loop on every rewrite.

- **Acceptance loop (P1)** — the turn after a rewrite, your reply is recorded per rule:
  `yes`→`accepted`, `edit …`→`edited` (a *positive* signal — coaching landed), `no`→`rejected`.
  A fresh unrelated prompt records nothing (no guessing at implicit rejections). Yields a
  per-rule **acceptance rate** = `(accepted + edited) / outcomes`.
- **Precision-gated activation (P2)** — a rule below `precision_floor` (0.15) over
  `min_outcomes_for_gating` (4) outcomes is demoted `dormant` and stops firing; an **explore
  slot** re-admits one dormant rule every `explore_period` (10) prompts. A **fatigue cap**
  (`max_nudges_per_window`, default 6 per 20) silences excess rewrites (still logged).
- **Decaying mastery (P3)** — mastery isn't terminal. A mastered rule carries a review clock on
  an expanding schedule (`review_intervals_days` = `[30, 90, 180]` days of non-use); each natural
  use resets + advances it. If it lapses, the rule decays to a `watch` tier and must be freshly
  re-demonstrated to re-graduate. Grounded in skill-decay + spacing-effect research.

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

## On-demand analysis — `/prompt-coach-beta:analyze` (v0.37+)

The passive hook is quiet by design — it only checks the few *active* rules. But the skill
carries the whole prompting-knowledge catalog, so you can point it at a prompt on demand and
get a **full-catalog read** (all 35 rules × 6 tiers + positive detectors), not just the active
subset.

Two modes:

- **A specific prompt** — *"analyze this prompt: refactor the whole auth module to be cleaner"*.
  You get every rule that fires (with its tier, the fix, and a clickable doc URL) plus a
  rewritten prompt that resolves the top issues.
- **Your recent history** — *"analyze my last 20 prompts"* / *"how have I been prompting?"*.
  Reads this repo's coach log, runs the full catalog on each, and reports your clean rate, the
  top recurring rules, and one habit to focus on next.

Backed by `config.py analyze "<text>"` / `analyze --last N` (add `--json` for raw data). The
slash command wraps it with a coached narrative. Read-only — never touches mastery or config.

```
$ …/config.py analyze "fix it and make it better and faster"
── prompt analysis ─────────────────────────────────────
  7 rule(s) fired (full catalog):
    · L1 vague-reference — Vague reference
    · L1 no-definition-of-done — No definition of done
    · L1 improve-without-metric — Improve without a metric
    · L2 no-verify-loop — No verify loop
    · L4 implicit-goal — Action without goal
    …
```

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
├── config.json        # global config (enabled, thresholds, disabled_rules)
└── state.json         # global mastery ledger: fires_total, clean_streak, status per rule

<repo>/.claude/prompt-coach/
├── config.json        # per-repo overrides (enabled, disabled_rules)
├── state.json         # per-repo fires_here, reactivations
└── log.md             # rolling log of nudges + prompt previews
```

## Verify it's on

- A rule-firing prompt should produce the inline `💬 prompt-coach` block at the start of
  Claude's response; a clean prompt produces the one-line `✓` heartbeat. Either way
  `.claude/prompt-coach/log.md` keeps growing.
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
