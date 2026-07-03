# prompt-coach-beta — evolution log (v0.1.0 → v0.18.0)

Consolidates 20 D&L entries from 2026-07-01 → 2026-07-03. In two days the plugin
grew from a first-cut heuristic (v0.1: 11 rules, one nudge mode) to a
well-instrumented coaching system with voice presets, LLM-composed alternatives,
and a structured config surface (v0.18: 28 rules, 22 config keys, 8 categories,
2 voices × 3 sources). This doc captures the timeline, the design principles
that emerged, and the key lessons — so CLAUDE.md stops overflowing.

## Timeline

| Version | Date | What | Why |
|---|---|---|---|
| 0.1.0 | 2026-07-01 | `UserPromptSubmit` hook; 11 rules × 3 tiers; global mastery + per-repo overrides; configurable mode | Prompt quality drives every downstream cost |
| 0.2.0 | 2026-07-01 | +13 rules: L3 classical (CoT, few-shot, rubric, uncertainty), L4 goals/loops, L5 tool-native (plan mode, TaskCreate, agents, roles, panel, Workflow) | v0.1 missed advanced concepts |
| 0.4.0 | 2026-07-01 | +21 positive detectors with sparing praise (Kohn/Dweck/Fogg); milestone events (mastery, first-after-fire); +L6 skill-awareness (rule of three) | Coach should also cheer, and know its own ecosystem |
| 0.5.0 | 2026-07-02 | Levenshtein typo pre-pass on ~90 trigger words; adaptive tolerance | Dyslexic-friendly; rising fallback rate self-reports catalog gaps |
| 0.6.0 | 2026-07-02 | Conversational short-circuit (approvals / multi-choice / continuations); praise_ratio default 10→3 for trial visibility | Coach misfired on `sure` / `1 and 2` |
| 0.7.0 | 2026-07-02 | Log-mined 34 prompts: inflection guard kills 5/6 bad corrections; +15 action verbs; +L2 no-answer-shape; praise_ratio reverted 3→10 | Evidence over guessing |
| 0.8.0 | 2026-07-02 | `/prompt-coach-beta:stats` slash command; broadened cited-context/stated-goal; new grounded-scope positive | 0 positives fired in 34 prompts (dark layer) |
| 0.9.0 | 2026-07-02 | Refresher tier: mastered rules still evaluate, fire rarely (50-prompt cooldown); softer refresher box; opt-in auto-demotion | Mastery ≠ permanent silence |
| 0.10.0 | 2026-07-02 | `nudge_style="inline"` renders nudge as opening block of Claude's response | TUI hook-stderr rendering is unreliable |
| 0.11.0 | 2026-07-02 | Hedge stripping (`try to / let's / need to`); +deploy/publish/release/ship action verbs | `try to deploy` fired nothing |
| 0.12.0 | 2026-07-02 | `no-answer-shape` elevated L2→L1; broader question regex; +`commit` verb; `max_active_rules` cap 5→6 | 5 info-seeking prompts missed |
| 0.13.0 | 2026-07-03 | `"coach that was wrong"` bug-flag phrase; `/report-issue` command with first-5-words redaction + structural signature | User-driven bug loop |
| 0.14.0 | 2026-07-03 | `/prompt-coach-beta:help` card: live version, resolved config, commands, say-it phrases, state file pointers | Discoverability |
| 0.15.0 | 2026-07-03 | 75-entry log audit: +8 hedges, +`run/review` action verbs, tighter `check` DoD, broader no-role critique. 5/7 gaps closed | Continued coverage tuning |
| 0.16.0 | 2026-07-03 | Anti-habituation: variant pool (3/rule) + novelty rotation + progressive disclosure + silence-after-saturation. Voice rewrite (technical → colleague) | Same message every fire (Hattie & Timperley, Sasse & Rashid) |
| 0.16.1 | 2026-07-03 | Fixed 3 code paths rendering variant list literal; SKILL.md drift (tier count, no-answer-shape tier, defaults); help.md v0.16 knobs | Doc/code out of sync post-v0.16 |
| 0.17.0 | 2026-07-03 | `voice_preset` (colleague / plain, L1+L2 both, L3-L6 fall back); `voice_source` (static / llm-compose / hybrid) with 6 anti-disagreement guardrails; medium/short inline static bug fix | Non-native readers + user-noticed LLM-composed disagreement |
| 0.18.0 | 2026-07-03 | `/prompt-coach-beta:config`: show/get/describe/set/reset/diff/export. `CONFIG_SCHEMA` metadata (22 keys × 8 categories); deep-merge preserves forward-compat keys | Config knob count outgrew ad-hoc say-it phrases |

## Design principles that emerged

1. **Evidence over guessing.** Every rule change from v0.7 onward was driven by
   log audits of real prompts (34 in v0.7, 75 in v0.15). The
   `normalization_stats.tokens_corrected_total` fallback count is itself a
   self-report signal on where the catalog is thin.

2. **Sparing, specific, process-focused praise** (Kohn/Dweck/Fogg). Praise
   dilutes at high frequency; specific > generic ("you attached a metric to
   'better'" beats "great prompt"); process > trait ("that's a well-scoped ask"
   not "you're a good prompter"). Variable-ratio (Skinner) keeps it potent.

3. **Anti-habituation is variety + capping + escalation** (Hattie & Timperley
   2007 on feedback wear-out; Sasse & Rashid 2013 on alert fatigue; ad-tech
   creative wear-out research). Four ingredients: variant pool, novelty
   rotation, progressive disclosure (full → medium → short), silence after
   saturation (5 fires in 30 prompts → 30-prompt silence).

4. **Deterministic by default, LLM-composed on request.** `static` source is
   0 cost and reproducible. `llm-compose` costs +200-800 ms and ~150-400 tokens
   per fire but produces situated feedback. `hybrid` gives static for the
   teaching moment and llm-compose for repeats.

5. **Guardrails prevent LLM disagreement** — six baked into the `llm-compose`
   `additionalContext`: header verbatim, word-count cap by disclosure level,
   must not override the rule (even if context resolves the referent), must
   match the preset voice, must end on a concrete ask, prompt shape provided so
   Claude can situate the response.

6. **Config metadata as single source of truth.** `CONFIG_SCHEMA` sits
   alongside `DEFAULT_CONFIG` in the analyzer. Every future option is picked up
   automatically by the `/config` dashboard, describer, and validator. Deep-merge
   writes preserve unknown keys (forward-compat across versions).

## Key lessons

- **The medium/short inline paths in v0.16 quietly let Claude improvise the
  nudge text.** For two weeks, Claude was paraphrasing from `rule.guidance`
  instead of rendering preset variants, occasionally *disagreeing with the
  rule* ("this referent's clear from context, proceeding"). Fixed in v0.16.1
  by embedding the picked variant text verbatim in the `additionalContext`.
  The user noticing this failure mode is what turned into v0.17's `llm-compose`
  feature (with anti-disagreement guardrails baked in).

- **Voice matters and isn't self-evident.** Original v0.16 variants were
  technical-manual voice ("heavy verbs invite over-reach", references to
  Chesterton's fence). External review flagged them as artificial. Rewrote all
  18 L1 variants in "colleague giving quick feedback" voice. Later expanded to
  two full presets (`colleague`, `plain`) so non-native speakers have an
  idiom-free option.

- **Say-it phrases + structured commands both work.** Natural language
  (*"set prompt-coach to inline"*) stays the fast path. `/config` is the
  discoverable surface when the user doesn't know what the options are called.
  They're not competing — they're complementary.

- **A growing config catalog demands metadata.** By v0.17 there were 20+ keys
  and no way to introspect them programmatically. The v0.18 `CONFIG_SCHEMA`
  approach (metadata alongside defaults, single source of truth) means the
  next 20 keys cost one dict entry each.

- **Symlink dev-link + inline mode unblocks tight iteration.** `make dev-link`
  points the marketplace cache at the source repo, so edits to
  `analyze-prompt.py` land without reinstalling. `nudge_style: inline` shows
  the actual behavior in the transcript, catching bugs like the medium/short
  disagreement mode that were invisible under `both`.

## Future direction

- **Java MCP server** — living design spec at
  `plugins/prompt-coach-beta/docs/java-mcp-spec.md`. Prerequisite is
  multi-user training data; `/report-issue` already produces the shape
  (structural signature + first-5-words + user annotation).
- **`plain` preset expansion to L3–L6** — currently falls back to
  `colleague`. Add plain variants as evidence surfaces which L3–L6 rules fire
  most for plain-preset users.
- **`voice_source` telemetry** — every fire logs
  `p=<preset>:src=<source>`. Once enough fires accumulate, `/stats` will
  surface which combination the user converges on.
