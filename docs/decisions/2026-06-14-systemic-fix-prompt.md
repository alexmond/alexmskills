# Systemic-fix prompt — draft

A reusable instruction nudging Claude to look past the local symptom when fixing
a bug: check the *scope* (other instances), name the *class*, and consider a
*structural prevention*. The discipline is to **report before patching** and
default to a small fix — without that, the rule degenerates into refactor
sprawl on every typo.

Open: where this should live (CLAUDE.md convention vs slash command vs ad-hoc
paste). Possibly a tiny beta plugin if it earns its keep across repos.

## Draft prompt

> When you find a bug, treat the local fault as **one instance**, not the whole
> problem. Before proposing a fix, check three things:
>
> 1. **Scope** — grep for the same pattern elsewhere. The same anti-pattern in
>    another file is almost always the same bug.
> 2. **Class** — name the kind of mistake (off-by-one, missing null check,
>    unhandled error, wrong API, race, leaked resource, etc.).
> 3. **Prevention** — is there a structural change — a helper, a type, a lint
>    rule, an API signature, a test — that would make this *class* of bug
>    impossible to reintroduce?
>
> Report findings *before* patching: list the other instances you found, name
> the class, and propose a structural option if one exists — each with a
> one-line recommendation. Let me pick: **local fix only**,
> **fix-all-instances**, or **structural change**. Default to local-fix-only
> unless the evidence is strong; never silently expand scope.

## Direction (2026-06-15): self-calibrating standalone skill

The draft above is the right *behavior*, but the right *form* is a small skill
that calibrates to the repo on first run, the way `tune-repo` does. Decided
after the sibling-repo survey: real bugs live in places like jhelm's
sprig/helm/core boundaries — a one-size-fits-all "grep for the same pattern"
either misses sibling modules or sprawls project-wide. The skill should learn
the right scope per repo, then ask the user.

**It is a standalone skill, not a dev-crew extension.** Primary mode is solo:
invoked whenever Claude finds a bug, the user asks "is this systemic?", or the
`/systemic-fix` slash command runs. Composition with dev-crew (e.g. the `lead`
role delegating its scope+class steps) is one *optional* mode, not the
framing.

### What "first run" does

Scan the current repo once (write the result to `.claude/systemic-fix/profile.md`)
and capture:

- **Module map** — top-level source roots / submodules. The unit of "grep
  here first" comes from this.
- **Bug-class taxonomy** — labels already in use on the issue tracker (`bug:`,
  `parsing`, `regression`, …); CI-enforced lint rules (the ones whose findings
  are already auto-fixed, so don't qualify); the test framework (so
  prevention-via-test is concrete, not abstract).
- **Existing scope-discipline hooks** — pre-commit checks, custom lint rules,
  architectural fitness functions. These are the *prevention options* the
  skill already has at its disposal.

### Options the skill offers after the scan

Two of the three refinements become **user choices**, informed by the scan:

1. *Refinement #1 — scope of the grep.* Defaults to **same module → sibling
   modules → project-wide**, but the scan can collapse this (single-module
   repo) or expand it (per the module map). The user picks once; the skill
   remembers per repo.
2. *Refinement #2 — gating.* Defaults to **correctness bugs only**, but the
   scan offers the actual labels found on the tracker so the gate is concrete
   ("trigger on `bug:` + `regression:`; skip on `style:` + `docs:`").

### What stays dynamic (refinement #3)

The **report shape** is generated from the scan, not a fixed template:

- "Other instances" section lists by module, in scan-order, with file:line.
- "Prevention" options are drawn from the scan's discipline-hooks inventory —
  e.g. *"add a Checkstyle rule under `config/checkstyle/`"* in jhelm, or
  *"add an `ArchUnit` test under `…/architecture/`"* in builder — instead of
  the abstract "consider a structural change."
- The three-way choice (local / fix-all / structural) is rendered with the
  actual files and the actual rule paths, so picking is a one-token decision.

### Invocation modes

1. **Solo (default).** Triggers on any bug Claude finds during normal work,
   or on user phrases like "look wider", "is this systemic", "find related
   bugs". Works in any repo, with or without other plugins installed.
2. **Slash command.** `/systemic-fix` to run explicitly on a known bug;
   `/systemic-fix recalibrate` to redo the first-run scan.
3. **Crew composition (optional).** When dev-crew is installed, the `lead`
   role may delegate the scope+class steps to `systemic-fix` instead of
   re-deriving them. Opt-in, never the framing.
4. **Tune-repo pairing.** `tune-repo` may add the `systemic-fix` invocation
   phrase to a repo's `CLAUDE.md` as one of its tightening recommendations.

### Naming / packaging

- Plugin name (beta channel): `systemic-fix` (verb-first kebab-case, fits
  convention). Companion to `tune-repo` (one-shot calibration) and
  `evolving-claude-md` (ongoing maintenance). No dependency on dev-crew.
- First-run prompt: "I'll scan the repo to learn its module map and bug
  classes. ~30s, read-only."

## Open questions (carried forward)

- Does the first-run scan re-run automatically on big structural changes
  (new module appears, lint config moves), or only on demand via
  `/systemic-fix recalibrate`?
- Profile location: standalone at `.claude/systemic-fix/profile.md` (default;
  no cross-plugin coupling), or — when dev-crew is also installed —
  *optionally* read additional context from `.claude/dev-crew/PROFILE.md`
  to avoid re-scanning. Solo install must never depend on dev-crew
  artifacts.
- Crew composition shape (only when dev-crew is installed): plug into
  `lead`'s investigation step, a new dev-crew hook, or stay fully external
  and just be invoked separately?
