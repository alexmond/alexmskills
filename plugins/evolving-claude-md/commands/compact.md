---
description: Compact CLAUDE.md's Decisions & Learnings — graduate durable lessons, drop release mirrors, merge, split, archive the rest. Proposes first, applies on approval.
argument-hint: "[plan | yes]"
---

# `/evolving-claude-md:compact`

Run the four downward pressures on this repo's Decisions & Learnings log as one
reviewed edit. `plan` stops after showing the plan. `yes` skips the approval
step. Anything else (or nothing) proposes, then waits.

CLAUDE.md is the project's working memory, so **nothing is rewritten unseen**,
and **nothing is deleted without a trace**: archived entries go to
`docs/decisions/`, graduated ones leave a line pointing at the rule.

## 1. Get the plan

From the directory holding `CLAUDE.md`, run the planner (read-only):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/evolving-claude-md/compact-claude-md.py"
```

If `CLAUDE_PLUGIN_ROOT` is unset, use the newest installed copy:
`ls ~/.claude/plugins/cache/*/evolving-claude-md/*/skills/evolving-claude-md/compact-claude-md.py | sort -V | tail -1`.

No `### Decisions & Learnings` section → stop and offer the skill's setup
("make CLAUDE.md evolve") instead; there is nothing to compact.

Then read the whole Decisions & Learnings section and the Conventions /
Gotchas sections — every judgment below needs the actual text, not the
planner's previews.

## 2. Draft the edits, in this order

The order is the point. Graduation must happen **before** age-out, or a lesson
that should be a standing rule goes into the quarterly archive instead.

1. **Supersede gaps** — strike the named target, or fix the link.
2. **Release mirrors** — an entry that names a version `CHANGELOG.md` already
   documents. Keep what the release **taught** — a constraint, a trap, a
   reversal, usually the `Why:` — and drop what it **shipped**. Rewrite the
   entry to the lesson, or drop it outright when it only says what shipped.
3. **Same-day clusters** — collapse to one entry *only* if it really was one
   piece of work. A busy day spanning unrelated tickets is not a cluster.
   Per-aspect detail goes to `docs/decisions/{date}-{topic}.md`.
4. **Graduation** — two sources:
   - the planner's tag candidates (same tag 3+ times, stable), and
   - **your review of every age-out entry**. The planner lists them because a
     lesson recurring by *theme* under different tags never trips the tag
     rule, and a log that tags each entry uniquely would otherwise graduate
     nothing. Ask of each: would a future session make a mistake without it?
   Each graduation is a one-line rule in **Conventions** (or **Gotchas** for a
   trap). Merge with an existing rule rather than adding a near-duplicate. If
   the file has neither section, propose adding the one you need.
5. **Mega entries** — keep a one-line teaser, move the detail to
   `docs/decisions/{date}-{topic}.md`.
6. **Stale candidates** — check the cited artifacts against the tree (grep,
   `git log -- <path>`). Fix the entry, strike it, or keep it with a note.
7. **Age-out** — last, mechanically: `archive-decisions.py --cutoff <date>`
   (the planner prints the exact command). It moves every entry on or before
   the cutoff to `docs/decisions/{YYYY-QN}.md` and leaves one teaser per
   quarter, merging with a teaser from an earlier run.

## 3. Propose

Show the edits grouped by step, with the **exact new text** for every rewrite,
graduated rule, and teaser, and the counts: entries / KB before and the
projected after. Keep it scannable; a long plan is fine, a vague one is not.

Unless the argument was `yes`, **stop and wait.** Accept "all", "skip
<step>", or edits to individual items.

## 4. Apply

1. Make the judgment edits with the Edit tool — the lint hook checks every
   entry you write. A rejection means fix the entry and retry, not bypass.
2. Write any `docs/decisions/` detail files the edits point at.
3. Run the archive dry-run, then the real one:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/evolving-claude-md/archive-decisions.py" --cutoff <date>
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/evolving-claude-md/archive-decisions.py" --cutoff <date> --apply
   ```

## 5. Report

Re-run the planner and report before → after (entries, KB, lines), what
graduated and where it now lives, and which `docs/decisions/` files were
written or appended. Don't commit — say what changed and let the user decide.

## Never

- Invent a rule the entries don't support. Graduation condenses evidence; it
  doesn't add policy.
- Archive before graduating.
- Delete an entry with no trace: it is either archived, struck with a reason,
  or replaced by a graduation line.
