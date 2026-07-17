---
description: Show current mastery — which rules mastered, which are in progress, which need reset. Enhanced analysis (v0.26+) flags untested masteries so you can spot rules that may be irrelevant to your patterns rather than truly internalized.
---

# `/prompt-coach-beta:mastery`

Direct top-level access to the mastery view. Same output as `/prompt-coach-beta:config mastery` but you don't have to type the `config` prefix.

## What to do

1. Locate the config script (same helper the other commands use):

   ```bash
   ls ~/.claude/plugins/cache/alexmskills/prompt-coach-beta/*/scripts/config.py 2>/dev/null | tail -1
   ```

   Fallback for dev checkout:
   `~/IdeaProjects/alexmskills/plugins/prompt-coach-beta/scripts/config.py`

2. Parse the user's input:

   | User says | Run |
   |---|---|
   | *(no arg)* | `python3 <path> mastery` |
   | *"as JSON"* / *"json"* | `python3 <path> --json mastery` |
   | *"reset <rule-id>"* | `python3 <path> mastery-reset <rule-id>` (dry-run first, then ask to confirm) |
   | *"reset all"* / *"reset everything"* | `python3 <path> --dry-run mastery-reset-all`, show preview, ask to confirm |

3. **Render the script's stdout verbatim.** The output already has the
   analysis section built in (v0.26+): mastery evidence quality (well-tested
   vs barely-tested vs untested), untested masteries listed with a
   suggestion, and close-to-mastery rules surfaced.

4. Calibrated follow-up (≤2 sentences):

   - **Many untested masteries** (≥5) → note that this often means the rules
     don't apply to how you prompt, not that you've internalized them.
     Suggest picking one to reset if the user wants active coverage.
   - **Rules close to mastery** → mention them; a couple more clean prompts
     and they graduate.
   - **Zero mastered rules** → first-time user; explain that mastery is
     *earned by demonstration*: a rule masters once you actually use its good
     technique (its positive detector fires) `min_demonstrations` times
     (default 3) with no recent relapse — clean streaks alone no longer master
     a rule.

## Natural-language routing

| Prompt | Route |
|---|---|
| *"show mastery"* / *"my mastery"* / *"how am I doing"* | `mastery` |
| *"check my mastery"* / *"analyze mastery"* | `mastery` |
| *"which rules mastered"* | `mastery` (analysis section covers it) |
| *"reset <rule-id>"* | `mastery-reset <rule-id>` |
| *"reset all my mastery"* | `mastery-reset-all` |
| *"is any of my mastery suspicious"* | `mastery` (analysis section flags untested) |

## What NOT to do

- Do NOT modify state files directly. Use `mastery-reset` / `mastery-reset-all`
  via the script — they preserve `prompt_count` and non-schema keys.
- Do NOT propose resets unprompted. The script's analysis suggests them; let
  the user decide.
- Do NOT enumerate every rule id in your follow-up. The script already renders
  the rules; your job is the 1-2 sentence coaching layer on top.
