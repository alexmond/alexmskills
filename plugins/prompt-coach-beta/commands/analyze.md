---
description: Analyze a specific prompt (or your last N prompts) against the full rule catalog and coach improvements
---

# `/prompt-coach-beta:analyze`

On-demand prompt analysis. Unlike the passive hook — which only checks the handful of
*active* rules and stays quiet — this runs the **full 34-rule catalog + positive detectors**
against either a prompt you name or your recent prompt history, then coaches concrete
improvements using the skill's prompting knowledge.

## What to do

1. Locate the config script (same resolution as `/prompt-coach-beta:config`):
   `${CLAUDE_PLUGIN_ROOT}/scripts/config.py`, else the dev checkout path.

2. Route on the argument:

   | User intent | Run |
   |---|---|
   | analyze a prompt they pasted / "analyze this: <text>" | `--json analyze "<text>"` |
   | "analyze my last N prompts" / "review my last N" / "how have I been prompting" | `--json analyze --last N` (default N=10) |
   | analyze the prompt *before* this command (their previous turn) | read it from the transcript, pass as `analyze "<text>"` |

   Always pass `--json` (before the verb) and `--cwd <repo>` so you get structured data.

3. **Single prompt** → the JSON gives `fired[]` (each with id, tier, name, guidance, url) and
   `positives[]`. Produce a short coaching report:
   - If `clean: true`, say so and name any positive habits detected.
   - Otherwise, for each fired rule give a one-line "why it fired + the fix", then offer a
     **rewritten prompt** that resolves the top 2–3 issues. Cite the rule URLs (they're
     clickable). Keep the voice of the collaborator block: propose, don't preach.

4. **History (`--last N`)** → the JSON gives per-prompt `fired[]`, a `rule_frequency` map, and
   `rule_detail`. Produce a **pattern report**:
   - Lead with the clean rate (e.g. "6/10 fired no rule").
   - Name the top 2–3 recurring rules and what they mean, with their doc URLs.
   - Give ONE concrete habit to focus on next (the highest-frequency fundamental).
   - Optionally show the single worst prompt with a rewrite as a worked example.

5. Render the script's own output only if the user asked for raw data; otherwise fold it into
   your coaching narrative.

## Notes

- History reads **this repo's** log (`.claude/prompt-coach/log.md`), and prompts are stored as
  ≤400-char previews — analysis is on the preview, which is enough for pattern-spotting.
- This is read-only: it never changes mastery, config, or state.
- For cross-repo history, point the user at the standalone `log-review` skill ("say log
  review") — this command is single-repo.

## Examples

- *"analyze this prompt: refactor the whole auth module to be cleaner"* → full-catalog read +
  a rewrite that names the file set, the metric for "cleaner", and a guardrail.
- *"analyze my last 20 prompts"* → clean rate + top recurring rules + one habit to work on.
- *"was my last prompt any good?"* → read the previous turn from the transcript, analyze it,
  coach it.
