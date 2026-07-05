---
description: Show prompt-coach help — commands, config options, and say-it phrases
---

# `/prompt-coach-beta:help`

Print a compact help card for the coach. Read the current installed version and resolved
config to fill in the live values.

## What to do

1. Read `~/.claude/plugins/cache/alexmskills/prompt-coach-beta/*/. claude-plugin/plugin.json`
   (whichever version exists) for `.version` and `.description`.
2. Resolve current effective config by merging (in order): built-in defaults →
   `~/.claude/prompt-coach/config.json` → current repo's `.claude/prompt-coach/config.json`
   (if any).
3. Render the card below with the live values substituted.

## The card

Render as a fenced block so it presents like a dashboard, under 60 lines.

```
prompt-coach-beta v<VERSION>

A UserPromptSubmit hook that watches every prompt you send Claude Code and nudges
you toward better prompting habits. 34 rules across 6 tiers, 22 positive detectors,
typo tolerance, conversational + picker-answer short-circuit. Rules quietly
graduate as you master them and fade to occasional refreshers.

New to the coach? See SKILL.md's "Quick start" section — a 60-second setup,
what a nudge looks like, the four slash commands, and the most-used say-it
phrases. Path:
  ~/.claude/plugins/cache/alexmskills/prompt-coach-beta/*/skills/prompt-coach/SKILL.md

────────────────────────────────────────────────────────────────────
COMMANDS

  /prompt-coach-beta:stats           Health dashboard — prompts analyzed, emit rate,
                                     top-fired rules, mastery, typo corrections, config
  /prompt-coach-beta:mastery         Which rules mastered, which need reset — with
                                     analysis (well-tested / barely-tested / untested);
                                     surfaces close-to-mastery rules (v0.26+)
  /prompt-coach-beta:analyze         On-demand analysis (v0.37+): run the FULL 34-rule
                                     catalog against a pasted prompt or your last N
                                     logged prompts, with a coached rewrite / pattern report
  /prompt-coach-beta:config          Structured config surface — show / get / describe /
                                     set / reset / diff / export / mastery / sources
                                     (v0.18+)

  (Cross-repo daily review moved out in v0.23. Say "log review" or
   "daily review" to invoke ~/.claude/skills/log-review/ instead.)
  /prompt-coach-beta:report-issue    File a privacy-safe bug report for prompts the coach
                                     mistreated. Uses candidates.jsonl seeded by the
                                     say-it phrases below.
  /prompt-coach-beta:help            This card.

────────────────────────────────────────────────────────────────────
SAY-IT PHRASES (talk to Claude naturally; Claude edits the right file)

  On/off (v0.29+ — rendering is always inline):
    "disable prompt-coach"            set enabled: false in this scope
    "enable prompt-coach"             set enabled: true in this scope
    "coach pause 10"                  temporary silence for N prompts
    "reset prompt-coach mode"         drop local override (legacy — no-op post-v0.29)

  Voice (v0.17+):
    "set prompt-coach voice to colleague"  default — direct, ends on a question
    "set prompt-coach voice to plain"      simple English for non-native speakers
    "set prompt-coach source to static"    default — pre-written variants
    "set prompt-coach source to llm-compose" Claude writes a fresh, situated nudge each fire
    "set prompt-coach source to hybrid"    static on full fires, llm-compose on refreshers

  Pause / disable:
    "coach pause 10"                  silence for the next N prompts
    "coach off <rule-id>"             permanently disable one rule
    "coach on <rule-id>"              re-enable it
    "coach reactivate <rule-id>"      per-repo — re-open a rule that mastered globally
    "disable praise"                  silence encouragement, keep nudges
    "praise every N prompts"          set praise_ratio

  Flag a bad call (adds to candidates.jsonl for /report-issue):
    "coach that was wrong"            flags the PRIOR prompt for review
    "coach missed this"
    "coach false positive"
    "bad nudge" / "wrong nudge"

────────────────────────────────────────────────────────────────────
CURRENT CONFIG (resolved: default → global → this repo)

  nudge_style:                <live value>
  graduation_threshold:       <live value>  (clean prompts in a row → mastered)
  cooldown_prompts:           <live value>  (min between same-rule nudges)
  mastered_cooldown_prompts:  <live value>  (min between refresher fires)
  max_active_rules:           <live value>  (default 6)
  praise_ratio:               <live value>  (1 praise per N clean prompts w/ positive)
  praise_on_mastery:          <live value>
  praise_on_first_after_fire: <live value>
  disable_praise:             <live value>
  typo_tolerance:             <live value>  (0 disables normalization)
  disabled_rules:             <live value>
  demote_on_regression:       <live value>  (self-healing; off by default)

  Anti-habituation (v0.16+):
    saturation_threshold:     <live value>  (N fires in silence_window → silence)
    silence_window:           <live value>  (sliding window in prompts)
    silence_duration:         <live value>  (how long silence lasts)
    disclosure_medium_at:     <live value>  (fire count → medium box)
    disclosure_short_at:      <live value>  (fire count → one-liner)

  Voice (v0.17+):
    voice_preset:             <live value>  (colleague | plain)
    voice_source:             <live value>  (static | llm-compose | hybrid)

  Global config file:   ~/.claude/prompt-coach/config.json
  Per-repo config file: .claude/prompt-coach/config.json (per repo)

────────────────────────────────────────────────────────────────────
CONFIG OPTIONS REFERENCE

  nudge_style        both | silent | log-only | inline
                     both     — boxed nudge on stderr + Claude sees context
                     silent   — Claude sees, user doesn't
                     log-only — no external output; every fire logged
                     inline   — nudge rendered as opening block of Claude's response

  graduation_threshold      N clean prompts → rule masters (default: 15)
  cooldown_prompts          Min prompts between same-rule nudges (default: 5)
  mastered_cooldown_prompts Refresher cooldown for mastered rules (default: 50; 0=off)
  max_active_rules          Cap on practicing rules active at once (default: 6)
  pause_until_prompt        Skip nudging until global prompt_count > this
  disabled_rules            Array of rule ids to permanently silence

  praise_ratio              1 praise per N clean prompts w/ positive fire (default: 10)
  praise_on_mastery         Celebrate rule mastery events (default: true)
  praise_on_first_after_fire  Praise the immediate correction (default: true)
  disable_praise            Silence encouragement, keep nudges (default: false)

  typo_tolerance            Levenshtein edit-distance for typo normalization (default: 2)
  demote_on_regression      Object {enabled, threshold, window} — auto-demote mastered
                            rules that fire threshold+ times within window prompts.
                            Off by default.

  Anti-habituation (v0.16+):
  saturation_threshold      N fires in silence_window → silence rule (default: 5)
  silence_window            Sliding window in prompts (default: 30)
  silence_duration          How long silence lasts (default: 30 prompts)
  disclosure_medium_at      Fire count in window → medium box (default: 2)
  disclosure_short_at       Fire count in window → one-liner (default: 4)

  Voice (v0.17+):
  voice_preset              Which set of phrasings the coach draws from:
                              colleague  — default, direct, ends on a question
                              plain      — simple English for non-native speakers
                            L1+L2 ship both presets with 3 variants each; L3-L6
                            fall back to colleague when plain requested.
  voice_source              Who authors the nudge text at fire time:
                              static      — pre-written variants (default; 0 cost)
                              llm-compose — Claude writes fresh, situated to your
                                            prompt with 6 guardrails
                                            (+200-800ms, ~150-400 tokens/fire)
                              hybrid      — static on full fires, llm-compose on
                                            medium/short refreshers

────────────────────────────────────────────────────────────────────
STATE FILES

  Global mastery ledger:  ~/.claude/prompt-coach/state.json
  Per-repo state:         .claude/prompt-coach/state.json (this repo)
  Fire log (audit):       .claude/prompt-coach/log.md
  Bug-report candidates:  .claude/prompt-coach/candidates.jsonl

────────────────────────────────────────────────────────────────────
DOCS

  Full SKILL.md:  <plugin dir>/skills/prompt-coach/SKILL.md
  Sources:        <plugin dir>/docs/sources.md — bibliography per rule
  Marketplace:    alexmond/alexmskills → prompt-coach-beta
```

## What NOT to do

- Do NOT modify any state or config files as part of `/help`. Read-only.
- Do NOT enumerate every rule id (28 rules × 2-line description = wall of text). Point at
  `/prompt-coach-beta:stats` for active rules and mastered rules if the user asks for them.
- Do NOT run the coach's Python code — the help card is static content + config lookup, not
  a live analysis.
