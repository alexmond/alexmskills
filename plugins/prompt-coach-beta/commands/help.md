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
you toward better prompting habits. 35 rules across 6 tiers, 35 positive detectors,
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
  /prompt-coach-beta:analyze         On-demand analysis (v0.37+): run the FULL 35-rule
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

  Analyze / sources / files (v0.36+):
    "analyze this prompt: <text>"     full-catalog read + a coached rewrite
    "analyze my last N prompts"       pattern report over recent history
    "open the docs for <rule>"        open the Anthropic guide URL in a browser
    "show me the skill folders"       list plugin folders, state, runnable scripts

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

  enabled:                    <live value>  (master switch; false = fully off)
  ack_clean:                  <live value>  (✓ heartbeat on clean prompts)
  ack_ratio:                  <live value>  (1 = every clean prompt)
  show_source_urls:           <live value>  (clickable doc URLs in the coach block)
  min_demonstrations:         <live value>  (times you USED the technique → mastered, v0.40)
  regression_guard:           <live value>  (clean prompts since last fire, needed w/ demos)
  inactive_after:             <live value>  (clean_streak w/ 0 demos → inactive)
  graduation_threshold:       <live value>  (clean-streak recency signal; not the mastery driver)
  cooldown_prompts:           <live value>  (min between same-rule fires)
  mastered_cooldown_prompts:  <live value>  (min between refresher fires)
  max_active_rules:           <live value>  (default 6)
  praise_ratio:               <live value>  (1 praise per N clean prompts w/ positive)
  praise_on_mastery:          <live value>
  praise_on_first_after_fire: <live value>
  disable_praise:             <live value>
  tips_enabled:               <live value>  (proactive advanced-technique tips)
  typo_tolerance:             <live value>  (0 disables normalization)
  disabled_rules:             <live value>
  demote_on_regression:       <live value>  (self-healing; off by default)

  Global config file:   ~/.claude/prompt-coach/config.json
  Per-repo config file: .claude/prompt-coach/config.json (per repo)

────────────────────────────────────────────────────────────────────
CONFIG OPTIONS REFERENCE

  enabled                   Master switch. false = hook returns immediately (default: true)
  ack_clean                 ✓ liveness heartbeat on clean prompts (default: true)
  ack_ratio                 Emit the ack every Nth clean prompt (default: 1)
  show_source_urls          Full clickable doc URLs in the coach block (default: true)

  min_demonstrations        EARNED MASTERY (v0.40): times the mirroring positive must fire
                            — i.e. times you USED the technique — before a rule masters (default: 3)
  regression_guard          Clean prompts since last fire required alongside demos (default: 3)
  inactive_after            clean_streak with 0 demonstrations → rule retires inactive (default: 15)
  graduation_threshold      Clean-streak recency/decay signal; no longer drives mastery (default: 15)
  min_fires_for_mastery     Legacy v0.27 gate, superseded by min_demonstrations; ignored
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

  (v0.38 removed the legacy `nudge_style`, `voice_preset`/`voice_source`, and the
   anti-habituation keys along with the hand-written nudge path. The coach is
   collaborator-only: when a rule fires, Claude rewrites your prompt fresh, so
   there's no preset to pick and no repeated text to habituate to.)

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
