---
description: Aggregate prompt-coach activity across all repos and render a scannable daily brief
---

# `/prompt-coach-beta:daily-review`

Cross-repo daily analytics for the coach. Reads every `.claude/prompt-coach/log.md`
under a search root (default: `~/IdeaProjects`) plus the global mastery state,
and renders a brief covering volume, top-fired rules, positive detections, typo
corrections, per-repo activity, and any candidates queued for bug-reporting.

Complementary to `/prompt-coach-beta:stats`: `stats` shows a global point-in-
time dashboard; `daily-review` shows temporal activity across the fleet of
repos.

## What to do

1. Locate the analyzer script. It ships with the plugin:

   ```bash
   ls ~/.claude/plugins/cache/alexmskills/prompt-coach-beta/*/scripts/daily-review.py 2>/dev/null | tail -1
   ```

   Fallback to the source path if the user runs from a dev checkout:
   `~/IdeaProjects/alexmskills/plugins/prompt-coach-beta/scripts/daily-review.py`.

2. Parse the user's argument after `/prompt-coach-beta:daily-review`:

   Time-window modes (mutually exclusive, first match wins):

   | User says | Run |
   |---|---|
   | *(no arg)* / `today` | `python3 <path>` (defaults to today since local midnight) |
   | `yesterday` | `python3 <path> --yesterday` |
   | `week` / `last 7 days` | `python3 <path> --days 7` |
   | `last N days` | `python3 <path> --days N` |
   | `since YYYY-MM-DD` | `python3 <path> --since YYYY-MM-DD` |
   | `from YYYY-MM-DD to YYYY-MM-DD` | `python3 <path> --since YYYY-MM-DD --until YYYY-MM-DD` |

   Scope modifiers (append to any of the above):

   - "for repo X" / "just X" → `--repos <resolved-path>` (resolve the repo name to a filesystem path under the search root)
   - "under ~/code" / "search root ~/code" → `--search-root ~/code`
   - "as JSON" / "json format" → `--json`

3. **Render the script's stdout verbatim.** It's already formatted for the
   terminal — box-drawing bars, section headers, aligned columns. Do not
   restyle. If the exit code is non-zero, surface the stderr.

4. After rendering, offer one context-appropriate follow-up:

   - If **candidates are queued** → suggest running `/prompt-coach-beta:report-issue`
   - If **emit rate is high** (>20%) → suggest `/prompt-coach-beta:config mastery` to see the rules that keep catching
   - If **a rule is close to mastery** (streak 12–14) → point that out; a couple more clean prompts finishes it
   - If **the window is empty** → don't force a follow-up; just note the possible causes

   Keep the follow-up to ≤2 sentences; don't compete with the report body.

## Natural-language routing (examples)

| Prompt | Route |
|---|---|
| "daily review" / "how did I do today" | today |
| "how about yesterday" | `yesterday` |
| "last week's coach review" | `--days 7` |
| "review the coach for the last 30 days" | `--days 30` |
| "coach review just for alexmskills today" | today + `--repos ~/IdeaProjects/alexmskills` |
| "give me the raw json for the week" | `--days 7 --json` |

## What NOT to do

- Do NOT re-implement the aggregation. The script is the source of truth; if
  something looks off in its output, fix the script and re-run.
- Do NOT interpret the log lines directly. Regexes belong in `daily-review.py`.
- Do NOT modify any files. This command is strictly read-only across the
  fleet of repos.
- Do NOT enumerate every repo's log if `--repos` isn't set. The default
  search root (`~/IdeaProjects`) is the intended scope.
