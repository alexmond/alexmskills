---
name: conductor
description: >
  Use while running parallel agent lanes — when a lane reports back, when a scheduled check fires, or before merging a lane's branch. Also when the user says "check the lanes", "is that lane on track", "what's running", "did it actually do it", "why did this lane go red", "should I merge this", "start another lane", or "the agent didn't do what I asked". Detects lanes drifted from their brief and decides route-vs-relay-vs-pause.
---

# conductor

The conductor is the role the MAIN session adopts. Every other role is seated as a
subagent and accumulates lessons in its own file; the conductor is seated nowhere, so
**its learnings exist and nothing loads them.** That is the gap this skill closes: it is
the loading mechanism, and the place new lessons land.

`ticket-triage` schedules ACROSS tickets. This skill governs what happens WITHIN a run:
is this lane doing what it was told, and what do I do when it is not.

## First: read the accumulated learnings

```bash
cat .claude/conductor/learnings.md 2>/dev/null || echo "(none yet — this is a first run)"
cat .claude/roles/conductor.md 2>/dev/null | sed -n '/## Learnings/,$p'
```

**Read both before acting.** The installed plugin is a read-only cache; the repo's file is
where this run's lessons go. Skipping this step is not hypothetical: a conductor re-made
the *"never edit a tree while a gate is running on it"* mistake with a file that already
said so, in the same repo, because nothing put it in front of them.

## The measure problem — the failure that outranks all others

**A lane will satisfy the done-when you wrote, not the one you meant.** If the two differ,
the lane is not at fault and telling it so wastes the round.

Measured, one repo, one epic: **fourteen lanes, zero files moved.** The work was retiring
data files. Every brief said *"nothing reads this file any more"*; every lane achieved
that, honestly. The owner's actual measure was *the file has moved to its archive path* —
and a reader census satisfies the first while leaving the file exactly where it was.

The shape generalises past files: a done-when phrased as a PROPERTY ("it is no longer
used", "the API is consistent", "the config is centralised") is satisfiable by argument. A
done-when phrased as an OBSERVABLE ("this path no longer exists", "this query returns 0",
"this command exits non-zero") is not.

- **Write the done-when as something checkable by someone who was not in the
  conversation** — a path, a row count, an exit code, a diff. "Nothing reads it" is a claim
  about intention; `ls` is a fact.
- When a lane reports success, ask what would be **observably different** if it had done
  nothing. If the answer is "a test now asserts a property", that may be the whole
  deliverable — or it may be the lane routing around the work.

## Four deviation shapes, with what each looks like from outside

### 1. The control that pins the blocker in place

A lane asked to remove an obstacle instead writes a test asserting the obstacle holds.
It passes, it looks rigorous, and it makes the next lane's job harder. Measured: a lane
briefed to retire a legacy table shipped a control asserting that table's population was
non-empty — with the stated purpose that the retirement *may not proceed* while it held.
Merged, then reverted the same day, once someone asked whether anything still wrote to it.

**A test whose job is to refuse a direction the owner has chosen is not a control.**
Neither is a third control on a seam two controls already cover.

Route: tell the lane to **report the obstacle as a file and a line, not as a new artifact.**
A paragraph in a report is read now; a control outlives its reason and is quoted back as a
constraint.

### 2. The report that is evidence, not fact

Lanes are right more often than not, which is exactly why an occasional wrong claim gets
merged. **Verify anything load-bearing yourself, before merging.**

Measured: a lane reported repointing a script. It had — **one of its five path defaults.**
The conductor excluded that script from a control's exemption set on the strength of the
report, and the control caught it on the next gate. The file was one `grep` away.

- A claimed fix to a broken artifact: **run the artifact.**
- A claimed control: **re-run it against the pre-fix state.** Ask for the red-before-green
  output, not the green run. A test never shown to fail pins nothing.
- Check the branch's **file list** against what the lane said it changed. It catches another
  lane's work swept in, and it costs one command.
- A surprising negative deserves the same scrutiny as a surprising positive.

### 3. The stale premise — the most expensive brief defect there is

The lane trusts what you wrote and builds on it before discovering it is false.

Measured, two false premises in one brief. *"Two of the three deployments hold no copy of
this file"* — they held tracked EMPTY stubs, so the hazard the brief dismissed (a scaffold
command writing the file back) was real and invisible under that wording. And *"these 14
rows are orphans"* — all 14 pointed at live records. The lane measured both and corrected
them; a lane that had trusted the brief would have shipped on top of both.

- **Say which of your facts you measured and which you inherited.** "I verified these
  myself; do not inherit my guesses — measure anything else you rely on" is what lets a
  lane correct you cleanly, and they will.
- When a lane corrects you, **check it, then say so plainly.** Correcting the brief is the
  lane doing its job.

### 4. The collision only visible after both merge

File partitioning stops two lanes editing one line. It does not stop two lanes making
claims about a tree that exists only after both land.

Measured: two lanes each removed one entry from a shared manifest and kept the other's —
git merged both cleanly and the result was wrong. Separately, both independently set a
counter to 27 when the true post-merge value was 26; it was loud only because the constant
was asserted against a derived count.

- **Partition by what will COLLIDE, not what will be edited.** The dangerous overlap is a
  shared *assertion*, not a shared line.
- When two lanes each delete something from one list, the resolution is the **union of the
  deletions**, not either side.
- **Never weaken set equality to a subset check to make a merge pass.**
- A merge-check run against the `main` that existed *before* a sibling merged proves
  nothing about the tree you will actually ship.

## Routing: relay, re-scope, pause, or let it run

| signal | route |
|---|---|
| premise you gave it has changed | **relay**, immediately — it is building on it now |
| lane is doing good work on the wrong scope | **re-scope**, and say what is now out |
| lane needs a decision only the owner can make | **pause that lane**, surface the decision, keep the others running |
| lane is right and you were wrong | say so, adjust the brief, do not re-litigate |
| lane is slow but on track | **let it run** — a check-in that demands a status costs a round trip and buys nothing |

**A relay is a decision.** Log it at send, in the round file, one line — not from memory
three tool calls later. A rule that depends on narrating a call you made earlier breaks
exactly when the round is busy, which is when relays happen.

**Findings flow lane → conductor → lane, never lane → lane.** Two lanes agreeing directly
produce an arrangement you then merge and cannot explain.

**Pause the lane, not the round.** One blocked lane is not a reason to stop the others.

### What NOT to relay

- **Commits behind, with no file overlap.** The trigger is overlap; "you are behind" is
  something a lane cannot act on, and a rebase spent on it is a gate thrown away.
- A style preference you did not put in the brief.
- A question you can answer yourself with one command.

## Watch the lane's shape, not just its words

Cheap signals, no round trip:

- **Uncommitted file count against commit count.** A lane at 28 modified files and 1 commit
  is one process death from losing the round. Measured: one lane died with 13 commits and
  lost nothing; the next sat at 186 modified files and zero commits. Relay *commit as you
  go, red commits included* — a red commit on a branch is recoverable, an uncommitted tree
  is not.
- **An agent that exited while its gate still runs.** The verdict arrives with nobody to
  read it. Adopt it: wait on the pid, read the verdict, merge or report yourself.
- **A lane whose branch has grown work its report does not mention.**

## Reading a verdict you did not run yourself

- **Never take the exit code of a piped command.** `check | tail` reports `tail`'s status,
  so a red verdict reads as green. Read the check's own verdict LINE, or run it unpiped.
- **A pass can prove nothing.** Check the run's own report of what it *covered* — a suite
  whose data was absent skips everything and still prints PASS.
- **An assertion quoting text that is not in `HEAD` is a tree that changed under the
  build**, not a defect in the commit being tested. The usual cause is a second process
  mutating the same working tree.
- **Never edit, merge into, or commit to a tree while a check is running on it.** The
  verdict then describes neither the before nor the after.

## The parallelism ceiling is a measurement, not a preference

Find the machine's real limit and hold it. Measured on one 24-core box: five concurrent
full builds was sustainable; **six put load at 54 and killed three of them.** Dispatching
into a machine already at the ceiling costs more than waiting.

Hold a lane's gate rather than let it be the one that breaks the machine — and tell it
explicitly to wait for a re-gate signal, or it will sit idle believing it is blocked.

## The two-tier split: this skill is GENERIC, the learnings are PER-REPO

Everything above is portable — it describes how lanes deviate and how to route them, and
it must stay free of any one repo's nouns. **Every concrete fact belongs in the consuming
repo**, because the installed plugin is a read-only versioned cache and because a rule
about one repo's schema is useless in the next.

| tier | lives in | holds | who writes it |
|---|---|---|---|
| **generic** | this SKILL.md, in the plugin | deviation shapes, routing, verdict reading, the ceiling *as a method* | upstream, when a lesson holds across ~3 repos |
| **per-repo** | `.claude/conductor/learnings.md` | this machine's numbers, this repo's instruments, this owner's measure | every run |
| **graduated** | `.claude/roles/conductor.md` → `## Learnings (core)` | per-repo lessons that have held ~3 runs | you, pruning the tier above |

**The test for which tier a lesson belongs in:** strip the repo's proper nouns. If a rule
survives — *"a lane's report is evidence about intent, never about a file's contents"* — it
is generic. If it evaporates — *"deployment X holds an empty stub"* — it is per-repo. A
generic entry with a repo noun in it is a per-repo entry that escaped.

**Numbers are almost always per-repo.** "Five concurrent builds is this machine's ceiling"
is a fact about 24 cores and one build's memory appetite; the generic rule is *measure the
ceiling and hold it*. Do not upstream a number.

### The per-repo file

```bash
mkdir -p .claude/conductor        # first run in a repo
cat .claude/conductor/learnings.md 2>/dev/null   # every run, before acting
```

Append one line per lesson:

```
- YYYY-MM-DD — <what happened> → <what changes next time>.
```

- **Lead with the rule, not the story.** The narrative belongs in the round file.
- **Only what a future run can act on.** "A lane was slow" is not a learning.
- **Prefer a measured number to an adjective** — "six gates put load at 54 and killed
  three" outlives "too many gates is bad".
- **Name the instrument, not just the lesson** — that is most of what makes an entry
  per-repo rather than generic. *Advice:* "read the verdict line". *Usable, from one repo's
  file:* "`<the repo's gate script>` prints its verdict as a line, not an exit code, so a
  pipe reports the pipe's status and a red verdict reads as green."
- **A lesson about the repo's schema, paths or domain is NOT a conductor lesson** — it
  belongs in that repo's `CLAUDE.md`. This file is about running lanes.

### Graduating upstream

A per-repo lesson that recurs **in a different repo** is a candidate for this SKILL.md.
Two repos is a coincidence; three is a pattern. When you upstream one, strip every proper
noun first and keep the measurement as an anonymised *"measured, one repo"* — which is the
form every example above already takes.

## Composition

- **`ticket-triage`** schedules across tickets; this governs within a run. Its round file is
  where relays and lane state are logged.
- **`roles`** supplies the persona substrate. `.claude/roles/conductor.md` is where
  graduated learnings land.
- **`dev-crew`** runs one relay-worthy ticket through gated phases.

All optional; this skill degrades to generic agents and a single repo.
