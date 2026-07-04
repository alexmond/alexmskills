---
description: View or edit prompt-coach config — categorized dashboard, per-key describe/set/reset, diff, export
---

# `/prompt-coach-beta:config`

Structured surface for the coach's growing config catalog. Backs onto a schema
of every option (category, type, default, allowed values, description, example,
since-version) so new options are picked up automatically when they're added.

## What to do

1. Locate the config script. It's shipped in the plugin cache:

   ```bash
   ls ~/.claude/plugins/cache/alexmskills/prompt-coach-beta/*/scripts/config.py 2>/dev/null | tail -1
   ```

   If not present, fall back to the source path if the user is in a dev checkout:
   `~/IdeaProjects/alexmskills/plugins/prompt-coach-beta/scripts/config.py`.

2. Parse the user's input after `/prompt-coach-beta:config`:

   Direct verbs (run the script and render its output):

   - `<empty>` or `show` → run `python3 <path> show` in the current cwd
   - `show <category>` → `python3 <path> show <category>` (categories: output, voice, rule-activation, mastery, praise, typo-tolerance, anti-habituation, llm-fallback)
   - `get <key>` → `python3 <path> get <key>`
   - `describe <key>` → `python3 <path> describe <key>`
   - `options <key>` → `python3 <path> options <key>` (lists legal values with per-choice explanations)
   - `set <key> <value>` → `python3 <path> set <key> <value> --scope <scope>`
     (scope defaults to `global` unless the user says "in this repo" / "for this repo" → then `--scope repo`)
   - `reset <key>` → `python3 <path> reset <key> --scope <scope>`
   - `reset-all` → `python3 <path> reset-all --scope <scope>` (require explicit confirmation before running without `--dry-run`)
   - `diff` → `python3 <path> diff`
   - `export` → `python3 <path> export`
   - `mastery` → `python3 <path> mastery` (dashboard of mastered / in-progress / dormant rules)
   - `mastery-reset <rule-id>` → `python3 <path> mastery-reset <rule-id>` (dry-run once first)
   - `mastery-reset-all` → `python3 <path> mastery-reset-all` (dry-run once first, require explicit confirmation)

   **Interactive flows (Claude-orchestrated via AskUserQuestion):**

   - `quick` → walk the user through the ~4 categorical settings (`voice_preset`, `voice_source`, `nudge_style`, `praise_ratio`) with multiple-choice pickers. For each key:
     1. Run `python3 <path> options <key> --json` to get the current value + choices + descriptions
     2. Present via AskUserQuestion, header ≤12 chars (e.g. "Voice"), each option's label = the value, description = the first ~60 chars of the choice_description
     3. If the user picks a value different from current, run `python3 <path> set <key> <picked> --scope global`
     4. If they skip (choose "Other" and type nothing) or pick current, do nothing for that key
   - `full` → same pattern but walk EVERY schema key. For enums use AskUserQuestion. For int/bool ask a single AskUserQuestion with options ["Keep current: X", "Type a new value", "Reset to default (Y)"]. If they choose "Type a new value", ask in a follow-up. Skip keys where their current value already matches the default AND they haven't asked for a full walk-through explicitly. This is a longer flow — offer to skip categories the user isn't interested in.

3. Common flags:

   - `--dry-run` on set/reset/reset-all/mastery-reset* → show what would change without writing
   - `--scope global` (default) or `--scope repo` → which config file
   - `--json` → machine-readable output (for scripting)

3. Common flags:

   - `--dry-run` on set/reset/reset-all → show what would change without writing
   - `--scope global` (default) or `--scope repo` → which config file
   - `--json` → machine-readable output (for scripting)

4. Render the output verbatim. It's already formatted for the terminal — do not
   restyle. If the exit code is non-zero, surface the stderr message.

## Natural-language routing

Users often say what they want rather than typing the exact verb. Route these
to the appropriate command:

| User says | Run |
|---|---|
| "show me the config" / "what are the current settings" | `show` |
| "what's <key>" / "current <key>" | `get <key>` |
| "explain <key>" / "what does <key> do" | `describe <key>` |
| "what options are there for <key>" / "what modes exist" | `options <key>` |
| "set <key> to <value>" / "change <key> to <value>" | `set <key> <value>` |
| "reset <key>" / "unset <key>" / "clear my <key> override" | `reset <key>` |
| "show me what I've changed" / "list overrides" | `diff` |
| "back up my config" / "print my resolved config" | `export` |
| "start over" / "reset everything" | `reset-all` (require confirmation!) |
| "walk me through settings" / "help me pick" / "quick setup" | `quick` (interactive) |
| "walk me through everything" / "configure everything" | `full` (interactive, longer) |
| "show me my mastery" / "what have I mastered" / "how am I doing" | `mastery` |
| "reset my mastery on <rule>" / "reset <rule> mastery" | `mastery-reset <rule>` |
| "reset all my mastery" / "start mastery over" | `mastery-reset-all` (require confirmation!) |

## Safety

- **Always** dry-run first when the user says something ambiguous like "reset the coach" — call `reset-all --dry-run` to show what would be lost, then ask before proceeding.
- Never edit the config JSON directly with Write. Always use the config script — it validates against the schema, preserves unknown keys, and reports what changed.
- If `set` returns a validation error (bad value, not in choices, wrong type), relay the exact error message verbatim; don't try to guess a valid value.

## What NOT to do

- Do NOT enumerate the schema by hand. The script reads it from `analyze-prompt.py`; if you print your own list it will drift.
- Do NOT hardcode the plugin cache path — resolve it with the `ls` glob above so it survives version bumps.
- Do NOT run the coach itself (`analyze-prompt.py`) — this is a read/write on the config JSON only, not a live analysis.
