---
description: File a privacy-safe bug report about a prompt the coach mistreated or missed
---

# `/prompt-coach-beta:report-issue`

Help the user file a redacted bug report about a prompt the coach handled badly.
**Never file automatically** — the user must explicitly confirm the payload before
`gh issue create` runs.

## Step 1 — Read the flagged queue

Read `.claude/prompt-coach/candidates.jsonl` in the current repo (each line is a JSON entry
with `flagged_at`, `mark_phrase_first_5_words`, `target_log_line`). If it's missing or
empty, tell the user:

> No flagged candidates yet. To flag a prompt, say *"coach that was wrong"* / *"coach missed
> this"* / *"coach false positive"* / *"bad nudge"* on the turn immediately after a
> mistreated prompt, and it'll appear here.

Then stop.

## Step 2 — Parse each candidate

For each candidate line, parse `target_log_line` — it's the coach log format:

```
- [ts] fired=[...] chosen=... positives=[...] mastered=[...] corrected=[...] praise=... outcome=... prompt=«<first 400 chars of the flagged prompt>»
```

Extract: timestamp, fired rules, chosen rule, positives, corrections, outcome, and
`prompt` (which is already truncated to 400 chars but IS the flagged content).

## Step 3 — Compute a structural signature (PRIVACY-CRITICAL)

For each candidate, run through the *shape* of the prompt so the report describes it
without leaking it. Compute these locally (`python3 -c ...` is fine):

- word_count, char_count
- **first_5_words only** (never more)
- starts_with_action, starts_with_hedge
- has_file_ref, has_ticket_id, has_backticks, has_url
- has_goal_clause, has_guardrail_clause, has_dod_marker, has_format_spec
- is_question

The analyzer has a `compute_signature(prompt, corrections)` function you can invoke:

```python
python3 -c "
import sys, json
sys.path.insert(0, '<path-to>/plugins/prompt-coach-beta/scripts')
# rename hyphen for import
import importlib.util
spec = importlib.util.spec_from_file_location('ap', '<path-to>/scripts/analyze-prompt.py')
ap = importlib.util.module_from_spec(spec); spec.loader.exec_module(ap)
print(json.dumps(ap.compute_signature('<first 400 chars>', [])))
"
```

Or just compute the booleans by hand from the prompt — they're straightforward regex checks.

## Step 4 — Present each candidate to the user

Show a compact card per candidate:

```
Candidate #1  (flagged 2026-07-02T22:33:00Z)

Coach analysis:
  fired:      [vague-reference]
  chosen:     vague-reference (nudged:both)
  positives:  none
  corrections: publish→polish

Structural signature:
  9 words, 47 chars
  starts_with_action: false (hedge: "try to")
  has_file_ref: no    has_ticket_id: no    has_url: no
  has_goal_clause: no    has_guardrail_clause: no    has_dod_marker: no
  is_question: false

Redacted preview (first 5 words):
  "try to deploy prod service"
```

## Step 5 — Get user's annotation per candidate

For each candidate the user wants to report, ask:

> What did you expect the coach to do here? (One-line: *"expected no-plan-mode-for-risky
> to fire — deploy is risky"* / *"vague-reference was a false positive; context resolved
> it"* / *"missed the compound-tasks pattern"* etc.)

Optionally ask what class it is:
- **false positive** — coach fired but shouldn't have
- **false negative** — coach missed a real pattern
- **wrong rule** — coach fired the wrong rule
- **bad message** — nudge wording was unclear/confusing
- **redundant** — coach fired on a prompt already handled by another mechanism

## Step 6 — Assemble the report body

Combine all confirmed candidates into ONE issue body, in this format:

```markdown
# prompt-coach bug report

**Plugin version:** <read from `~/.claude/plugins/cache/alexmskills/prompt-coach-beta/*/.claude-plugin/plugin.json` `.version`>
**Report date:** <today>
**Candidate count:** <N>

---

## Case #1 — <ts>

**Class:** <false-positive | false-negative | wrong-rule | bad-message | redundant>

**Coach analysis:**
- Fired: <fired list>
- Chosen: <chosen> (<outcome>)
- Positives: <positives>
- Corrections: <corrections>

**Structural signature:**
- <word_count> words, <char_count> chars
- starts_with_action: <bool> (hedge: <bool>)
- has_file_ref / has_ticket_id / has_backticks / has_url: <bool bool bool bool>
- has_goal_clause / has_guardrail_clause / has_dod_marker / has_format_spec: <bool bool bool bool>
- is_question: <bool>

**Redacted preview (first 5 words):**
> "<first 5 words>"

**User annotation:**
> <user's one-line explanation>

---

## Case #2 — ...

... (repeat for each candidate the user included)

---

**Notes for the maintainer:**
- Reporting mechanism: /prompt-coach-beta:report-issue slash command.
- Full prompts intentionally omitted for privacy — only shape + first 5 words.
- Coach version: <plugin_version>
```

## Step 7 — PREVIEW to the user (blocking, no send)

Show the ENTIRE assembled report body to the user in a code fence, then ask:

> **Ready to file this to `alexmond/alexmskills` as a GitHub issue labeled `prompt-coach`?**
> The exact content above is what will be posted. Nothing else. Reply "yes" to file, "edit"
> to tweak the annotations, or "no" to cancel.

Wait for a `yes`. Anything else — do not file.

## Step 8 — File the issue

On explicit `yes`:

```bash
gh issue create \
  --repo alexmond/alexmskills \
  --title "prompt-coach report — N cases (<class-summary>)" \
  --label "prompt-coach" \
  --body-file <path-to-body.md>
```

If `--label prompt-coach` fails ("label not found"), create the label first:
```bash
gh label create prompt-coach --repo alexmond/alexmskills --color "5319e7" --description "prompt-coach coach bug reports" 2>/dev/null || true
```

Then re-run the create.

## Step 9 — Prune the candidates.jsonl

On success, either:
- Delete the flagged candidate entries from `.claude/prompt-coach/candidates.jsonl` (rewrite
  the file with only the entries NOT reported), or
- Move the file to `.claude/prompt-coach/candidates.jsonl.reported-<ts>` as an archive.

Print the issue URL from `gh issue create` output to confirm.

## What NOT to do

- **NEVER paste raw prompt content into the issue body beyond first_5_words.** Full prompts
  are captured in the coach's local log.md for the user's own debugging; they must not
  travel over the network as part of an issue.
- **NEVER file without explicit "yes"** from the user on the preview payload.
- **NEVER auto-select candidates.** The user picks which to include.
- **NEVER modify the coach's rules or code as part of this workflow** — that's a separate
  code change. This command only files reports.
