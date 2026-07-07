---
description: Show prompt-coach health metrics — fires, praises, corrections, mastery, active rules
---

# `/prompt-coach-beta:stats`

Read the coach's state files and log to produce a compact health dashboard.

## What to do

1. Read the global state at `~/.claude/prompt-coach/state.json`:
   - `prompt_count` (total analyzed globally)
   - `normalization_stats.prompts_with_corrections`, `.tokens_corrected_total`, `.top_corrections` (highest 5 by count)
   - `rules[*]` — for each: `status`, `fires_total`, `clean_streak`, `graduated_at` (if any)
2. Read the current repo's state at `.claude/prompt-coach/state.json` (if present):
   - `prompt_count` (this repo)
   - `reactivated` (per-repo rule reactivations)
3. Read the current repo's log at `.claude/prompt-coach/log.md` (if present):
   - Count `outcome=nudged:*` / `outcome=collaborator:*` (rewrite events)
   - Count `outcome=capped:*` (rewrites silenced by the fatigue cap, v0.41+)
   - Count `outcome=praised:*` (praise events, broken out by kind: `mastery`, `first-after-fire`, `variable-ratio`)
   - Count `outcome=skipped:conversational` (short-circuited)
   - Count `outcome=no-emit` / `outcome=ack:*` (analyzed but nothing fired)
4. **Acceptance ledger (v0.42+)** — run
   `python3 <plugin>/scripts/config.py acceptance` (or `--json acceptance`) for
   the acceptance rate: how often rewrites are taken (accepted + edited) vs
   rejected, globally and per rule. `edited` counts as a hit; `blind` rejects
   (too fast to have read) are excluded from the rate. Surface the overall
   rate + any rule flagged `⚠ dormant-risk` (low acceptance → will be
   precision-gated out of firing).

## Present as

```
prompt-coach v0.8.0 — <today's date>

Volume (global): <prompt_count>
Volume (this repo): <this_repo_prompt_count>

Emit rate (this repo):
  nudged:  N     |  praised: M  (mastery: X, first-after-fire: Y, variable-ratio: Z)
  skipped: K     |  no-emit: L
  rate:    (N+M) / (N+M+L) = P% substantive prompts got signal

Rules:
  mastered (dormant):    <list rule ids graduated>
  active (up to 5):      <list rule ids currently practicing>
  most-fired top 5:      <rule: N fires>

Acceptance (v0.42+):
  accepted A · edited E · rejected R · blind B  →  rate P%
  dormant-risk: <rules with low acceptance, if any>

Typo normalization (global):
  <prompts_with_corrections> prompts had corrections (<tokens_corrected_total> tokens)
  top 5 corrections: <original: count>

Config in effect (this repo):
  nudge_style: <both / silent / log-only>
  praise_ratio: <n>
  typo_tolerance: <n>
```

Keep it under 30 lines. Use monospace / a code fence so it renders as a dashboard, not prose.

## When to suggest tuning

- If `typo_tolerance` false-positive rate is climbing (5+ questionable entries in top_corrections), suggest adding them to `_PROTECTED_ENGLISH_WORDS` upstream.
- If a rule has fired 0 times in >100 prompts, suggest disabling it in `disabled_rules`.
- If any rule has `clean_streak > 30`, suggest it's over-mastered and would benefit from being re-tightened.
- If emit rate is < 10%, suggest the ruleset is under-covering the user's actual prompts and needs broader triggers.

## What NOT to do

Do NOT change any state files, config files, or the plugin itself as part of this command. Read-only report.
