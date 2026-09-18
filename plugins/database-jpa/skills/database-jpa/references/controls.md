# Controls that hold

Schema work fails silently more often than loudly. These are the properties that
separate a check from a comment with better formatting.

## Show it RED first

A green test that has never been shown to fail pins nothing. Before trusting a
new control:

- plant the defect it exists to catch, watch it fail **naming the plant**
- revert, watch it pass

Do this even when the defect is "obvious". A control has been shipped that could
not fail, more than once — including one whose regex ran over comment-stripped
source and so never saw the string literals it was searching for.

## "It passed" and "it ran" are different facts

A scan that resolves the wrong directory satisfies its rule forever. Every scan
asserts its own population:

- a **floor** on how many files/modules/rows it reached
- a **known positive** inside the sweep, asserted by name
- for a multi-module scan, one class named from **each** module

A scan whose population is empty must fail, not pass.

## Derive, never tabulate

A list of modules, tables, or files is a list that goes stale on the next move —
silently, and green. Derive from the tree (`git ls-files`, reflection over the
class that owns the fact, the poms themselves). Where something must be named,
name it **once** and assert that name still resolves.

If you inherit a hand-maintained table, give it a control that fails loudly when
it is stale.

## Exemptions must be self-closing

An exemption that outlives its reason is worse than none. Every entry:

- names the file **and** the artifact it excuses, not a directory
- asserts the reason still holds — the file still exists, still mentions the
  thing, the ignore rule still ignores it
- states its **kind**: a settled architectural decision, or a finding parked
  behind an open ticket. A parked finding recorded as a decision silences the
  control rather than informing it. A parked entry names the ticket that closes it.
- is capped in number, because an exemption map suppresses a signal

## Beware the flattering population

A check measured over a bigger population than the enforcing one always reads
better locally than it will in CI — coverage over a suite where data-dependent
tests actually ran, a lint over a tree with extra files. **A local FAIL is
trustworthy; a local PASS is not.**

Make the measurement name its own population beside every figure it prints, and
provide a mode that reproduces the enforcing population exactly.

## Never mask an exit code

`cmd | tail -n` reports the exit status of `tail`. Redirect to a file and read
`$?`, or read the tool's own verdict line. A failing build reported as passing
is the same class of defect as everything else in this file.

## Nested working copies poison whole-repo scans

A scan rooted at the repository root walks this checkout *plus every nested git
worktree*, each a full copy of an older revision. It then passes for the author
(a worktree has no worktrees inside it) and fails on the trunk. Filter out
dot-directories, build output, and dependency directories through **one shared
predicate**, not a private copy per scan.
