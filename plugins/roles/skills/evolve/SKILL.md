---
name: evolve
description: Audit + refine the role files in `.claude/roles/` so role personas keep improving after the first graduation. Surfaces consolidation candidates (≥3 Learnings entries on one topic → propose merge), staleness candidates (Learnings citing files/symbols that no longer exist), Body drift (cumulative learnings contradict the Charter/Body), and solo→core graduation candidates. All proposals are user-gated — the skill never silently rewrites a role file. Use when the user says "evolve roles", "audit roles", "consolidate role learnings", "refresh roles", "what should we graduate", or "roles are getting stale". Runs proactively too — periodically when many sessions across a repo have appended to role files. Complements (doesn't replace) the SessionStart `roles-init-audit.py` hook, which is reactive and lightweight; this skill is on-demand and deeper.
---

# Evolve Roles

> **Try it:** `/roles:evolve` — or say "audit the roles and propose refinements".

Graduation gets a learning *into* the role file. **Evolution** is the loop that keeps it useful afterwards: learnings consolidate as the same lesson recurs in new forms; entries go stale when the artifact they cite is renamed or removed; the Charter and Body drift out of date when the cumulative learnings have effectively re-shaped how the role behaves. Without this loop a role file calcifies — every new run appends, nothing refines, and after enough sessions the file is a layered archaeology no future reader will trust.

This skill runs that loop. **Never silently rewrites a role file.** Every proposal is shown to the user with the evidence; the user accepts, edits, or rejects each one.

## When to invoke

Trigger phrases:
- "evolve roles", "audit roles", "audit the role files", "refresh roles"
- "consolidate role learnings", "the `skeptic` role is getting noisy", "compact the role files"
- "what should we graduate", "what learnings should lift to core"
- "are any role learnings stale", "does the charter still match"

Also invoke proactively when the SessionStart `roles-init-audit.py` hook surfaces high solo-learning counts (>15 per role) or cross-orchestrator usage signals — those are reactive nudges; this is the deeper pass that *acts* on them.

Don't invoke for one-off "add this learning to the role" edits (the orchestrator that produced the lesson appends directly to the registry row or Learnings section — no audit needed for a single new entry).

## The four audit dimensions

For each role file in `.claude/roles/` (skipping consumer registries `crew.md` / `panel.md` / `research.md` / `registry.md`), run all four:

### 1. Consolidation candidates

When the same topic appears in ≥3 `Learnings (core)` entries — same artifact, same failure mode, same recurring critique — propose a single merged rule that captures the load-bearing pattern, and a proposed strike-through of the three originals.

Detection signal: clustering of backticked artifacts (same `ClassName.method` or `path/to/file` cited across multiple entries), or repeated lead phrases ("always", "never", "remember that").

Threshold: 3+ entries on one topic. Below that, individual entries still carry distinct nuance worth keeping.

### 2. Staleness candidates

When a `Learnings` entry cites a backticked artifact (path, class, method, flag) that no longer exists in the consuming repo's tree — `git grep -qF` over the tree comes up empty — propose strike-through, with a one-line follow-up if the entry's underlying lesson is still relevant under a new name.

Uses the same artifact-extraction heuristic as `evolving-claude-md`'s staleness trigger (paths, `ClassName.method`, `--cli-flags`, `<xml-tags>`, known-extension filenames). Conservative — only flags when ≥2 cited tokens are missing, to avoid false positives from prose-y backtick use.

### 3. Body drift candidates

When the cumulative `Learnings (core)` has effectively re-shaped how the role behaves but the `Charter` and `Body` sections still describe the older behavior, propose a Body / Charter refresh — with the specific learnings that motivated each proposed change shown alongside.

Detection signal: keywords in Learnings that contradict the Body's wording ("actually does X" / "Body says Y but in practice Z") or new responsibilities clearly accreted across multiple learnings that aren't in the Body's list.

Threshold: ≥3 learnings that collectively contradict or extend the Body. Below that, treat as ordinary accumulation.

### 4. Solo → core graduation candidates

When `Learnings (solo)` has ≥3 entries on the same topic AND the role is referenced in 2+ consumer registries (`crew.md` / `panel.md` / `research.md`), propose lifting the consolidated lesson into `Learnings (core)`. Shared use signals context-independence; multiple solo entries signal that the pattern is real, not a one-off.

The existing SessionStart hook (`roles-init-audit.py`) already surfaces high solo counts and cross-orchestrator usage as a reactive nudge; this dimension is the *action* on those nudges.

## The output contract

The skill writes its proposals as a single audit report — never as direct edits to the role files. Two acceptable forms:

- **Inline conversation** (default) — the assistant lists proposals in chat, the user accepts / edits / rejects each, and the assistant applies the accepted ones with explicit Edits.
- **`.claude/roles/audit.md`** (when the audit surface is large — ≥5 role files with proposals, or ≥3 proposals per role) — write a single audit file with one section per role; the user works through it at their pace; the assistant applies accepted proposals on a follow-up turn.

Each proposal carries: the **dimension** (consolidation / staleness / drift / graduation), the **evidence** (the offending lines / counts / cited-but-missing tokens), the **proposed change** (concrete diff), and a **reversal note** (how to undo if the lesson re-emerges).

## What the script does

`scripts/evolve-roles.py` is the audit engine. Run it from the consuming repo root:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/evolve-roles.py [--role <name>] [--apply] [--out audit.md]
```

- `--role <name>` — audit only one role file (default: all in `.claude/roles/`).
- `--apply` — write accepted proposals after the user has confirmed them on a separate channel; default is report-only, never edits.
- `--out <path>` — write the audit to a file instead of stdout (the skill picks this when the surface is large).

The script does *not* call an LLM. It uses regex + `git grep` (same as `evolving-claude-md`'s staleness check), wall-clock budget-capped so a large `.claude/roles/` tree never stalls. Each role file is audited independently; one bad parse doesn't fail the rest.

## What this does NOT do

- **Doesn't graduate from log to role file.** That's the orchestrator's job — `brainstorm-panel` Step 6, `dev-crew` self-learning loop, `research-sweep` step 9. This skill picks up *after* graduation has landed wisdom in the role file.
- **Doesn't apply silently.** Every change is user-gated, even staleness strikes (a "missing" token may be a deliberate forward-reference).
- **Doesn't propose new roles.** Minting new roles is the orchestrator's job under its own "mint a new role" protocol. This skill refines existing ones.
- **Doesn't merge across role files.** If two roles (`reviewer` and `refactorer`) have overlapping learnings, that's a role-design question for the user — not a mechanical merge.

## Common failure modes

- **Auditing a role file the user is mid-edit on.** Check `git status` first; skip role files with uncommitted changes (the user owns them right now).
- **Over-aggressive consolidation.** Three entries on one topic might be three distinct facets of the topic worth keeping separate. The user has veto.
- **Strict-staleness false positives.** A renamed class triggers the same flag whether the rename is the *new truth* or a bug. Always propose strike + a follow-up, never delete outright.
- **Treating Charter rewrite as cosmetic.** A Charter change re-shapes the role's behavior across every consumer. Show the user the *evidence* (which learnings motivated it), let them write the new Charter themselves if they want.

## The loop

Periodicity: run on demand, or roughly once per quarter alongside the `evolving-claude-md` archive pass. The SessionStart audit (`roles-init-audit.py`) provides the *signal* (here are the roles that need attention); this skill is the *action* on that signal.

A role file that has gone through one evolve pass reads like a *current* description of how the role actually behaves now, not like a layered archaeology of every lesson ever appended. That's the test: would a reader new to this repo, opening `.claude/roles/skeptic.md` cold, understand what the skeptic does today — or are they reconstructing it from sediment?
