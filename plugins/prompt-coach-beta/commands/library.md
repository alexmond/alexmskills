---
description: Find a gold-standard prompt template from Anthropic's Claude Code Prompt Library for a task
---

# `/prompt-coach-beta:library`

Look up the closest **gold-standard prompt template** from Anthropic's
[Claude Code Prompt Library](https://code.claude.com/docs/en/prompt-library) for
a task you describe — turning the coach from *corrective* ("here's what's wrong
with your prompt") into *generative* ("here's the canonical prompt for what you
want to do"). Offline: matches against a vendored snapshot, no network at call
time.

## What to do

1. Locate the plugin's `scripts/config.py` (installed cache path
   `~/.claude/plugins/cache/alexmskills/prompt-coach-beta/*/scripts/config.py`,
   else the dev checkout).
2. Route on the argument:

   | User intent | Run |
   |---|---|
   | "library for `<task>`" / "show me a prompt for `<task>`" | `--json library "<task>"` |
   | "what's in the prompt library?" / no argument | `--json library` (taxonomy) |

   Always pass `--json` (before the verb) and `--cwd <repo>`.

3. **A task query** → the JSON gives `matches[]`, each with `cat`, `sdlc`,
   `roles`, `_score`, and `_filled` (the template with its `{slots}` filled by
   Anthropic's example values). Present the top 1–3:
   - Show each template verbatim (it's the copy-paste-ready prompt).
   - Note its category / phase / role tags.
   - Offer to **adapt the top one to the user's actual context** (swap the
     example slot values — file paths, formats — for theirs) and run it.
   - Cite the source URL (it's Anthropic's library, vendored with attribution).

4. **No query** → the JSON gives `count`, `categories`, `phases`. Summarize the
   taxonomy (5 SDLC phases, 15 categories) and invite a task lookup.

## Notes

- The snapshot lives at `data/prompt-library.json`; refresh it with
  `scripts/gen-prompt-library.py` (fetches the live docs page). It is Anthropic
  documentation content, vendored with attribution — not this plugin's work.
- Read-only: this never changes config, mastery, or state.
- The coach ALSO uses this matcher passively: when a rule fires and
  `library_hints` is on (default), the collaborator rewrite is grounded in the
  closest library template's phrasing + slot structure.

## Examples

- *"show me a prompt for reviewing my auth changes"* → the `Review` templates
  (subagent security review / uncommitted-change review), offered adapted to the
  user's file paths.
- *"is there a library prompt for debugging a failing test?"* → the `Debug`
  template "the {test} is failing, find out why and fix it", filled with the
  user's test name.
- *"what's in the prompt library?"* → the phase/category taxonomy + an invite.
