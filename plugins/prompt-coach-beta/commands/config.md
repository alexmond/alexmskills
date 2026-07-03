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

   - `<empty>` or `show` → run `python3 <path> show` in the current cwd
   - `show <category>` → `python3 <path> show <category>` (categories: output, voice, rule-activation, mastery, praise, typo-tolerance, anti-habituation, llm-fallback)
   - `get <key>` → `python3 <path> get <key>`
   - `describe <key>` → `python3 <path> describe <key>`
   - `set <key> <value>` → `python3 <path> set <key> <value> --scope <scope>`
     (scope defaults to `global` unless the user says "in this repo" / "for this repo" → then `--scope repo`)
   - `reset <key>` → `python3 <path> reset <key> --scope <scope>`
   - `reset-all` → `python3 <path> reset-all --scope <scope>` (require explicit confirmation before running without `--dry-run`)
   - `diff` → `python3 <path> diff`
   - `export` → `python3 <path> export`

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
| "set <key> to <value>" / "change <key> to <value>" | `set <key> <value>` |
| "reset <key>" / "unset <key>" / "clear my <key> override" | `reset <key>` |
| "show me what I've changed" / "list overrides" | `diff` |
| "back up my config" / "print my resolved config" | `export` |
| "start over" / "reset everything" | `reset-all` (require confirmation!) |

## Safety

- **Always** dry-run first when the user says something ambiguous like "reset the coach" — call `reset-all --dry-run` to show what would be lost, then ask before proceeding.
- Never edit the config JSON directly with Write. Always use the config script — it validates against the schema, preserves unknown keys, and reports what changed.
- If `set` returns a validation error (bad value, not in choices, wrong type), relay the exact error message verbatim; don't try to guess a valid value.

## What NOT to do

- Do NOT enumerate the schema by hand. The script reads it from `analyze-prompt.py`; if you print your own list it will drift.
- Do NOT hardcode the plugin cache path — resolve it with the `ls` glob above so it survives version bumps.
- Do NOT run the coach itself (`analyze-prompt.py`) — this is a read/write on the config JSON only, not a live analysis.
