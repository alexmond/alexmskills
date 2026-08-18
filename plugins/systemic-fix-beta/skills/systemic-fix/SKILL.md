---
name: systemic-fix
description: >-
  Discipline for bug fixes: treats the local fault as one instance of a class, not the whole
  problem — checks scope (grep for the same pattern elsewhere, in a repo-calibrated search
  order), names the class of mistake, and proposes prevention drawn from the repo's actual
  lint/pre-commit/test tooling — reporting findings before any patch and defaulting to a
  local fix. Use whenever a bug is found during ordinary work, or when the user says "is
  this systemic?", "look wider", "find related bugs", "fix the class, not the instance", or
  runs `/systemic-fix` (`/systemic-fix recalibrate` redoes the calibration scan). On the
  first run in a repo it performs a ~30s read-only calibration scan (module map, bug-label
  taxonomy, existing discipline hooks) into `.claude/systemic-fix/profile.md` and lets the
  user pick the grep scope and gating once per repo.
---

# systemic-fix

When a bug is found, the default behaviour is to patch the line and stop. That misses two
things: the same anti-pattern usually exists in sibling files or sibling modules (ticking
regressions), and the bug is an *instance of a class* — a helper, a type, a lint rule, or a
test can make the class unreproducible, but only if someone names the class first.

The discipline is to **report before patching** and **default to the small fix**. Without
that default, the rule degenerates into refactor sprawl on every typo; without the report,
scope expands silently and the user finds out from the diff. Never silently expand scope.

## Gate — which bugs get the full loop

Correctness bugs only, by default: wrong behaviour, crashes, races, leaks, unhandled errors,
regressions. Skip style nits, doc typos, and anything a CI-enforced linter already auto-fixes
(those findings never reach a human, so they don't qualify as a class worth structural work).
The profile refines this gate with the labels the repo's tracker actually uses (see below);
when in doubt, run the scope check quietly and only surface a report if it finds something.

## First run — calibrate (read-only)

If `.claude/systemic-fix/profile.md` does not exist in the current repo, calibrate before
the first report. Tell the user: *"I'll scan the repo to learn its module map and bug
classes. ~30s, read-only."* The scan captures:

- **Module map** — top-level source roots / submodules. The unit of "grep here first".
- **Bug-class taxonomy** — labels already in use on the issue tracker (`bug`, `regression`,
  `parsing`, …); the test framework (so prevention-via-test is concrete); which lint rules
  CI already enforces (their findings are auto-caught and don't qualify).
- **Discipline-hook inventory** — pre-commit checks, custom lint rulesets, architectural
  fitness functions (ArchUnit-style tests). These are the prevention options the repo
  already has; a prevention proposal should extend one of them before inventing a new tool.

If dev-crew is also installed and `.claude/dev-crew/PROFILE.md` exists, read it as extra
context to avoid re-deriving the module map — but it is optional input, never a dependency;
a solo install works from the scan alone.

Then ask the user to pick **once per repo** (defaults derived from the scan):

1. **Grep scope order** — default `same module → sibling modules → project-wide`; a
   single-module repo collapses this to `project-wide`; a large monorepo may cap it at
   siblings.
2. **Gating** — default correctness-only, offered as the concrete labels found on the
   tracker (e.g. "trigger on `bug` + `regression`; skip on `style` + `docs`"). If the repo
   has no tracker labels, keep the generic gate.

Write the result to `.claude/systemic-fix/profile.md`:

```markdown
# systemic-fix profile — <repo>
calibrated: <yyyy-mm-dd>   (redo with /systemic-fix recalibrate)

## Grep scope (user-picked order)
1. same module          # e.g. core/
2. sibling modules      # e.g. sprig/, helm/
3. project-wide         # last resort

## Gating (user-picked)
trigger-on: bug, regression      # labels harvested from the tracker
skip-on: style, docs, typo

## Bug-class taxonomy
<tracker labels in use; recurring classes seen in recent fix commits>

## Discipline hooks (the prevention menu)
- lint: <e.g. config/checkstyle/checkstyle.xml — CI-enforced>
- pre-commit: <e.g. .pre-commit-config.yaml>
- architecture tests: <e.g. src/test/java/…/architecture/ (ArchUnit)>
- test framework: <e.g. JUnit 5 + Testcontainers>
```

## Every gated bug — the three checks

1. **Scope** — grep for the same pattern elsewhere, following the profile's scope order and
   stopping early when a level comes back clean. The same anti-pattern in another file is
   almost always the same bug.
2. **Class** — name the kind of mistake: off-by-one, missing null check, unhandled error,
   wrong API, race, leaked resource, stale cache, encoding mismatch, … Prefer a label from
   the profile's taxonomy so the name is greppable in the tracker later.
3. **Prevention** — is there a structural change that would make this *class* impossible to
   reintroduce? Draw the options from the profile's discipline-hook inventory, with real
   paths — "add a Checkstyle rule under `config/checkstyle/`", "add an ArchUnit test under
   `…/architecture/`" — not the abstract "consider a structural change". If the inventory
   has nothing that fits, a targeted regression test is the floor option.

## The report — before any patch

Generate the report from the profile, not from a fixed template: "Other instances" is
listed per module in scan order with `file:line`; "Prevention" names the actual hook files.
The three-way choice is rendered with the real files and rule paths so picking is a
one-token decision.

```markdown
## Systemic check — <one-line bug summary>

**Class:** missing null check on an optional config value

**Other instances** (scope: same module → siblings, per profile)
- core/   — src/main/java/…/ChartLoader.java:141
- sprig/  — src/main/java/…/DefaultFuncs.java:88
- helm/   — none

**Prevention options** (from the repo's discipline hooks)
- Checkstyle rule under config/checkstyle/ forbidding bare `.get()` on Optional
- regression test beside the existing loader tests

Pick one:
1. **local fix only** (default — recommended unless the evidence above is strong)
2. **fix-all-instances** (the 2 extra sites listed)
3. **structural change** (the Checkstyle rule, plus fix-all)
```

Wait for the pick. Default to **local fix only** when the user waves it through or the
evidence is thin (zero or ambiguous extra instances). A clean scope check still earns a
one-line report ("scope checked per profile: no other instances; class: …") so the user
knows the discipline ran — then proceed with the local fix without a gate.

## Recalibration

`/systemic-fix recalibrate` redoes the scan and the two choices on demand. The skill never
rescans automatically mid-bugfix; instead it flags staleness when it notices drift — the
bug lives in a module the profile doesn't list, or a named hook file has moved — and
suggests the recalibrate command in the report.

## Files this skill owns

All state lives in the **consuming repo**, never in the plugin directory (a
marketplace-installed plugin is a read-only cache; anything written there is lost on
update):

- `.claude/systemic-fix/profile.md` — the calibration profile + the two per-repo choices.
- `.claude/systemic-fix/log.md` — the append-only learning log (below).

## Learning loop

Append an entry to `.claude/systemic-fix/log.md` on every full run, and always on the two
failure modes:

- **Miss** — a sibling instance of a reported bug surfaces later that the scope check
  should have found. Record which module the scope order skipped.
- **False-systemic** — a fix-all or structural proposal the user rejected, or applied and
  then reverted. Reverts count double: they mean the gate or the evidence bar is too loose.

```markdown
## <yyyy-mm-dd> — <run | miss | false-systemic>
- bug: <one line>
- call: <local | fix-all | structural>; user picked: <same | overrode to …>
- evidence: <n extra instances in <modules> | clean scan>
- adjustment: <widen scope order | tighten gating | none>
```

When three entries point the same way (e.g. two misses in the same skipped module, or two
rejected structural proposals under the same label), apply the adjustment to
`profile.md` and note it in the log — that is the calibration tightening itself.

## Companions

- `tune-repo` — may add the systemic-fix invocation phrase to a repo's `CLAUDE.md` as one
  of its tightening recommendations.
- `dev-crew` — the `lead` role may delegate its scope+class investigation here instead of
  re-deriving it. Fully external and opt-in: no dev-crew hook, no shared state, and this
  skill works identically without it.
- `evolving-claude-md` — a graduated bug-class pattern ("this repo's recurring class is X")
  belongs in the repo's Decisions & Learnings, not in this skill's log.

## Graduation bar (beta exit)

This plugin graduates to `systemic-fix` when it has earned it, the way `prompt-coach` did —
measured, not felt:

- run on **10+ real bugs across 3+ repos** (different stacks, not one repo's bug streak)
- at least **3 runs** where the user picked fix-all or structural and **kept** the result —
  a reverted expansion is a false-systemic and counts against
- **zero** unresolved false-systemic entries in the log (each one must have produced a
  gating/scope adjustment)
- the first-run calibration needs **no manual correction** on 3 consecutive fresh repos

Track runs as dated entries below. When the bar is met: `make graduate
PLUGIN=systemic-fix-beta` + `make bump PLUGIN=systemic-fix VERSION=1.0.0`. If it stalls for
a quarter with no runs, retire it instead — an eternal beta is a catalog lie.

### Run log

(none yet — the bar starts counting now)
