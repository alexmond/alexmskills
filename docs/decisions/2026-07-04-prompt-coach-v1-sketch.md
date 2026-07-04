# prompt-coach v1.0 — design sketch

**Status:** design; not committed; consolidates the C+D + `no-mode` direction
we converged on across 2026-07-04.

## The one-line shift

**Pre-v1.0:** the coach is a rulebook — 34 regex rules fire on patterns and
emit hand-written coaching text. The user reads the nudge, mentally rewrites,
retypes.

**v1.0:** the coach is a collaborator — reads your prompt, applies the same
34 rules as *concepts*, and hands you a *rewrite* of your prompt with
improvements baked in. You Accept / Edit / Reject.

The nudge IS the rewrite. No separate "you did X wrong" step.

## Architecture: three stages

```
User prompt
  │
  ▼
┌─────────────────────────────────────────────────────────┐
│ Stage 1: regex fast-filter                    ~1 ms      │
│   34 rules keep their regex checks as broad recall.      │
│   Emits: candidate rule ids that MIGHT apply.            │
│   If 0 candidates → skip Stage 2, clean prompt is free.  │
└─────────────────────────────────────────────────────────┘
  │ (only fires on ~30% of prompts per current log data)
  ▼
┌─────────────────────────────────────────────────────────┐
│ Stage 2: LLM verify + rewrite (Haiku)  ~500 ms · ~$0.001 │
│   Input:                                                 │
│     - last 2-3 assistant turns from transcript           │
│     - current prompt                                     │
│     - candidate rule ids + rule concept descriptions     │
│     - user's mastery state (which rules are inactive)    │
│     - user's voice sample (last few prompts)             │
│   Output:                                                │
│     - confirmed_rules[] (regex fires that survive        │
│       context)                                           │
│     - vetoed_rules[] (regex fires context resolves)      │
│     - improved_prompt (the rewrite)                      │
│     - changes[] (one line per improvement)               │
│     - sources[] (anthropic_ref citations)                │
│     - confidence (0-1)                                   │
└─────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────┐
│ Stage 3: render inline, capture response signal          │
│   Show the rewrite + changes + sources inline.           │
│   User's next action (accept / edit / reject) records:   │
│     accept  → fires_total += 1, streak = 0               │
│     edit    → partial credit (adjust weights)            │
│     reject  → questionable_fire += 1                     │
└─────────────────────────────────────────────────────────┘
```

## Day-1 UX (what a user sees)

You type:

```
fix the login flow so it handles empty passwords
```

The coach renders (inline, always):

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💬 prompt-coach — read your prompt as:

    "in src/auth/login.js, update handleLogin() to reject empty
     password submissions with a 422 and a 'password required'
     message. Keep the existing test suite green."

Changes:
  [1] Named the file + function (was: 'the login flow')
  [2] Made the behavior explicit (was: 'handles empty passwords')
  [3] Added guardrail (existing tests stay green)

Sources: Anthropic — be clear and direct
         Anthropic — minimize hallucinations in agentic coding

Reply "yes" to proceed with this, "no" for original, "edit"
to change one line.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

(Because Claude Code's UserPromptSubmit hook can't do keypress
prompts, "Accept / Edit / Reject" is realized via the user's next
message — a short natural-language answer routed by the v0.24
picker-answer skip.)

## Config surface — 22 keys → 7 keys

| Key | Default | Purpose |
|---|---|---|
| `enabled` | `true` | Master switch (v0.29) |
| `graduation_threshold` | `15` | Clean prompts → mastery (v0.5) |
| `min_fires_for_mastery` | `1` | Evidence requirement (v0.27) |
| `mastered_cooldown_prompts` | `50` | Refresher rate on mastered rules (v0.9) |
| `disabled_rules` | `[]` | User-blocked rules |
| `llm_model` | `haiku` | NEW: which model runs Stage 2 |
| `llm_stage_confidence_min` | `0.6` | NEW: LLM confidence bar to fire |

Everything else deprecates.

## What survives from v0.29 (the bones)

- **34 rules** as concepts + regex fast-filter (Stage 1)
- **Rule tiers L1-L6** — still the pedagogical order
- **`sources.md` + `anthropic_ref`** — become citation footnotes on the rewrite
- **Mastery ledger** (fires_total, clean_streak, status, mastered_at, inactive)
- **Auto-migration** from v0.27 — inactive rules stay inactive
- **Log format** with `event=graduation` entries (v0.27)
- **Transcript-aware skips** — picker-answer + conversational
- **Bug-report queue** — `candidates.jsonl` + `"coach that was wrong"`
- **Slash commands** — `:config`, `:mastery`, `:stats`, `:help`, `:report-issue`
- **`enabled` master switch** (v0.29)

## What deprecates from v0.16-v0.28

Two full releases' worth of textual ceremony:

- **Voice presets** (colleague / plain — ~200 hand-written strings). LLM matches the user's voice from their transcript.
- **Voice source** (static / llm-compose / hybrid). Everything is LLM under v1.0.
- **Anti-habituation machinery** — variant pool, novelty rotation, progressive disclosure (full/medium/short), silence-after-saturation. Fresh LLM generation solves repetition at the source.
- **Tips catalog with hand-written bodies** (v0.28) — advanced techniques emerge from the rewrite ("the improved prompt already adds a few-shot example").
- **`_box`, `_refresher_box`, `_box_medium`, `_box_short`** — already dead in v0.29, deletable now.
- **Post-mastery fire tracking + demote_on_regression** — replaced by response-signal learning.
- **Disclosure levels** — the rewrite is one shape, tuned to the user's voice; no "medium box vs short box" split.

Net delete: ~500-700 lines of code + ~200 hand-written strings.

## Mastery becomes semantic

Currently `clean_streak` = "regex didn't fire on the last N prompts." That's why 18 of your 29 masteries were false — regex misses ≠ user internalized the technique.

Under v1.0, `clean_streak` = "LLM (with full history) confirmed no rules apply, OR user rejected a Stage 2 suggestion." Both mean "the user handled this competently in context."

`fires_total` = "user accepted a Stage 2 rewrite that named this rule."

`inactive` (v0.27) still means "rule never fired semantically" — the concept is unchanged; the measurement is now correct.

## Response signal → training data

Every prompt produces one of five signals:

| User signal | Meaning | Effect on rule state |
|---|---|---|
| Prompt was clean (no Stage 2) | Clean prompt in context | streak += 1 for all active rules |
| Stage 2 fires, user says "yes" | Confirmed useful | fires_total += 1, streak = 0 |
| Stage 2 fires, user says "no" | False positive | questionable_fire += 1 (nothing else moves) |
| Stage 2 fires, user says "edit" | Partial hit | fires_total += 0.5, streak = 0 |
| Stage 2 fires but user rejects same rule 3+ times | Rule doesn't fit them | Suggest adding to `disabled_rules` on next `/mastery` view |

`questionable_fires` becomes a first-class trainable metric — the coach learns which of its own rules are noisy for a given user.

## Java MCP server — what it actually does

The existing spec at `plugins/prompt-coach-beta/docs/java-mcp-spec.md` frames MCP as "port the Python to Java + add multi-user telemetry." Under v1.0, MCP has a different job:

1. **Hosts LLM inference** — batches Haiku/Sonnet calls, handles API keys, rate-limiting, cost caps
2. **Caches rewrite templates** — same prompt shape produces the same-shape rewrite; cache the LLM output for common patterns
3. **Cross-user rule weights** — a rule that gets vetoed by many users' contexts gets its trigger regex tightened globally
4. **Curriculum discovery** — sees which rules users master in what order; suggests progression
5. **Model choice** — Haiku vs Sonnet vs future models; version pinning; A/B experiments

That's real infrastructure, not translation. The MCP spec should probably get rewritten in this light — noted as a v1.0 dependency.

## Migration from v0.29 → v1.0

**Non-destructive.** On first v1.0 run:

1. Read existing global state
2. If `v1_migration_done` marker absent:
   - Existing masteries preserved (grandfather)
   - Voice preset silently dropped
   - Tip fires state preserved (retrospective analytics)
   - `nudge_style` legacy key silently dropped
   - Set marker
3. Add new keys with defaults (`llm_model: haiku`, `llm_stage_confidence_min: 0.6`)
4. Continue

Reversible via marketplace pin: `plugin.version: "<1.0.0"` in `.claude/settings.json`.

## Open questions

1. **Model default** — Haiku (fast + cheap, $0.001/prompt) or Sonnet ($0.02, higher-quality rewrites)? Probably Haiku default with a say-it phrase: *"use sonnet for coach"* to upgrade.

2. **Latency budget** — Haiku is ~500ms P50, ~2s P90. Adds up over a day. Users may want to opt into "regex-only mode" (`llm_stage: never`) for latency-sensitive work.

3. **Failure mode** — LLM API down? Fall back to v0.29 behavior (regex hits render hand-written text) or skip coaching entirely? Probably fall back — users shouldn't lose the coach if Anthropic has an outage.

4. **Rate limit / cost cap** — Users on personal API keys may want a monthly cap. Config: `llm_max_calls_per_day: 500`. Coach falls back to regex when exceeded.

5. **Privacy boundary** — Stage 2 sends prompt + assistant turns to Claude API. Currently the coach is 100% local. Some users will care; make it opt-in for the first month (`llm_stage_enabled: true` default, but bright banner on first run explaining what data flows where).

6. **Reject UX** — user rejects a rewrite → Claude proceeds with original. But now Claude's response is the next turn; there's no round-trip for "did that rewrite actually help?" Long-term signal quality is unclear until we have real data.

7. **Multi-line edits** — "edit" lets user say what to change in one natural-language line. Multi-line iterative refinement (like Cursor's inline edits) is out of scope for v1.0; too much UI surface.

## Testing before v1.0 ships

1. **Blind quality test** — 30 sample prompts, generate v0.29 nudge + v1.0 rewrite for each, blind-rate on "which is more useful next-step" and "which I'd want to see." Minimum bar: v1.0 wins ≥60% of the time.
2. **Latency** — measure Haiku Stage 2 P50 / P90 on real user traffic
3. **Cost** — track $/day for 500-prompt/day usage; verify caps work
4. **Failure gracefully** — kill the LLM API in staging; verify v1.0 falls back to v0.29 rendering cleanly
5. **Veto rate** — measure "regex fires but LLM vetoes" rate; if >20%, regex is too loose (tune)
6. **False positives from LLM** — measure "LLM says a rule applies but the user rejects." If >15%, LLM's context handling needs work

## Roadmap — not a leap, a sequence

| Version | Scope | Time |
|---|---|---|
| **v0.30** | Passive signal collection: coach reads back own transcript for "context resolves" / "false positive" phrases in Claude's responses; records `questionable_fires` per rule. Zero new deps. Produces training data. | 2 hours |
| **v0.31** | LLM veto pass: regex fires → Haiku called with history + candidate rule → returns "confirm" or "veto." Log outcome `nudged:verified` / `skipped:llm-vetoed`. Opt-in flag; default off. Measure veto rate + latency + cost. | 1 day |
| **v0.32** | LLM rewrite mode: new `coach_style: rewrite` config. When enabled, replaces the nudge with the rewrite. Legacy `coach_style: nudge` stays default. | 2 days |
| **v0.33** | Response-signal learning: capture accept/edit/reject; update `fires_total`, `questionable_fires` per rule based on user response. | 1 day |
| **v0.34** | Cost/rate caps + fallback modes: `llm_max_calls_per_day`, `llm_stage: [auto|never]`, `llm_failure_fallback: [regex|off]`. | 1 day |
| **v0.35-v0.40** | Polish, telemetry, deprecation warnings on old config keys, migration validator, MCP-server integration prep. | 2-3 weeks total |
| **v1.0** | Flip defaults to LLM-first. Delete deprecated textual ceremony. Java MCP server v1.0 ships in parallel and takes over inference for users who point at it. | Cut when v0.34+ has 2 weeks of positive evidence |

## What I want to hear back on

1. Does the day-1 UX feel right? Specifically the "reply yes / no / edit" pattern (given no keypress support in hooks).
2. **Model default** — Haiku or "let user pick"?
3. **Privacy** — opt-in or opt-out for Stage 2 LLM calls on first run?
4. **First step** — start with v0.30 (free passive signal) or leap to v0.31 (real LLM veto)?

Nothing about this sketch is committed. It's a designer's proposal to talk against, not a plan to execute.
