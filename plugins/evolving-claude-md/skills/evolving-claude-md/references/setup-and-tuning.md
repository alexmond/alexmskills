# Setup and tuning — evolving-claude-md

Reference material pulled out of SKILL.md so it loads only when you are
actually installing or re-tuning the skill, not on every trigger.

## Tuning the thresholds per repo

"Concise" is not a universal number. 40 KB is bloat in a library and reasonable
in a monorepo that genuinely has that much load-bearing context — so the shipped
defaults are a starting point, not a verdict, and every one is overridable.

Resolution order, later wins:

```
built-in defaults
  → ~/.claude/evolving-claude-md/config.json          (all your repos)
    → <repo>/.claude/evolving-claude-md/config.json   (this repo)
```

```json
{
  "file_warn_kb": 25,        "file_recommend_kb": 40,
  "lines_warn": 200,         "lines_recommend": 300,
  "entries_warn": 25,        "entries_recommend": 35,
  "mega_entry_chars": 800,   "topic_cluster": 3,
  "layout_min_dirs": 5,
  "coverage": true,          "nested": true
}
```

Name only the keys you want changed; the rest keep their defaults. Unknown keys
are ignored, and a corrupt config falls back to defaults rather than failing —
this runs on SessionStart, and a bad config file must never be the reason a
session starts badly.

Set `coverage: false` to drop the upward check, `nested: false` to stop looking
at companion files.

## Setup checklist (manual install)

For a fresh project, when not installing via the marketplace plugin:

1. Append the **How this file evolves** section to CLAUDE.md (a compact version of the rules above).
2. Seed the Decisions & Learnings split: `### Decisions & Learnings (Recent — last 14 days)` + an empty `### Historic` section.
3. Copy the four scripts into `.claude/skills/evolving-claude-md/`:
   - `audit-claude-md.py`
   - `freshness.py` (the staleness predicates — the audit loads it from its own directory)
   - `lint-claude-md.py`
   - `archive-decisions.py`
4. Add `.claude/settings.json` hooks pointing at them (SessionStart, PreToolUse, PostCompact) — see the plugin's `hooks/hooks.json` for the exact shape; replace `${CLAUDE_PLUGIN_ROOT}/skills/evolving-claude-md` with `.claude/skills/evolving-claude-md`.
5. Add the first real entry — usually the project goal.

The hooks need a single restart of the Claude Code session to register (settings reload). Installing as a plugin skips steps 3–4 entirely.
