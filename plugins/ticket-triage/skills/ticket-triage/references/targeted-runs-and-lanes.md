# Targeted runs and lane coordination

Detail behind two rules in SKILL.md. Load when running `triage <target>`,
or when more than one lane is in flight.

## Running toward a TARGET

`triage <target>` is the same loop with a different ranking key. The target is a
goal — an epic, a capability, a migration — not a ticket: *"get the city UI onto
the database"*, *"V16 work"*, *"batches migration"*.

**A target re-ranks; it does not filter.** Two rules, and they pull opposite ways:

- **A ticket that BLOCKS the target outranks its own label.** A p3 research ticket
  that nothing can proceed without is the top of the queue, and the label is
  evidence of what the filer knew, not of what the target needs. Say the promotion
  out loud, with what the target made true that the filer could not have known.
- **A rank-1 defect still preempts, target or not.** Data loss, a wrong answer
  served confidently, a broken instrument — these are not deferrable because they
  are off-target. Fix, then resume. Sequencing under a target is not a licence to
  step over a live defect.

**Name the blockers before dispatching anything.** A target with no stated blocker
list is a wish. Write down what must be true for the target to be reachable, then
rank *that* list — the backlog is a source of candidates, not the plan. Most of
the useful work in a targeted run is deciding what the target actually requires,
and that decision is usually wrong in the same direction twice: it under-counts
the DESIGN questions and over-counts the code.

**The target's own tickets are usually not enough.** Expect to file as you go:
work toward a goal surfaces defects the goal did not name, and those are often
better findings than the planned work. File them ranked and placed, and be
explicit about which ones are on the critical path versus merely discovered.

**Say what the target does NOT include.** A target attracts scope. The line
between "this advances the goal" and "this is adjacent and interesting" has to be
drawn out loud, per round, or the round never ends.

**Stop when the target is reached, not when the backlog empties.** Report against
the target: what is now true that was not, what remains, and what the next
increment costs. A targeted run that drains ten tickets without moving the goal
has failed, and should say so.


## Lanes that can see each other

File partitioning stops two lanes editing one line. It does not stop the failure
that actually happens: **two lanes make claims about a tree that will only exist
after both merge.** Observed shapes, all real:

- **A control and the thing it counts, in different lanes.** One lane writes a
  test asserting an exact set — tables with no writer, files with no author,
  declared authors. Another lane adds a member of that set. Each is correct alone;
  the merge is the first tree where both are true, and it is red. **Set equality is
  what makes this visible, and it must not be weakened to a subset check** — that
  would merge silently and leave the new members permanently unchecked.
- **A lane reasoning from another lane's UNMERGED branch.** A brief asserted a fix
  was in place; it was true only on a branch not yet in main. The lane measured,
  found it absent, worked around it, and said so — which is the good outcome, and
  only happened because the brief told it not to inherit the conductor's guesses.
- **One lane moving code out from under another.** A lane relocated two loaders;
  a second lane added imports for them. Merged: two unused imports, and a
  checkstyle failure with no obvious owner.
- **Two lanes solving the same problem for different artifacts**, each adding the
  same hook, where taking either side alone silently drops the other's input.

### The manifest

Before dispatch, write what each lane OWNS and what it will ADD:

- **paths it may edit** — the classic partition;
- **enumerating controls it will touch** — any test asserting an exact set. This is
  the collision surface that file lists miss, because the file is shared and the
  edit is a one-line list change;
- **shared registries** — decision logs, inventories, role files. Expect these to
  conflict on every round; resolve by keeping both sides, and check that the
  boundary between them did not cut a statement in half.

Repos that already have a session coordinator should use it rather than growing a
second one; the manifest is a *concept*, not necessarily a new file.

### Who may talk to whom (lanes do NOT talk to each other)

**Findings flow lane -> conductor -> lane, never lane -> lane.** This is
Anthropic's own finding from their multi-agent research system: subagents report
to the orchestrator, which synthesises and re-delegates. Two lanes negotiating
directly produce an agreement nobody else sees, and the conductor then merges an
arrangement it cannot explain.

- **A lane REPORTS what it needs from another lane's territory; it does not go and
  take it.** That rule already exists for files and it extends to facts.
- **The conductor messages a RUNNING lane when a premise it was given has
  CHANGED** — a measurement that moves its design, a decision the user took
  mid-flight, a sibling's finding that makes its approach wrong. That is
  orchestrator -> subagent, it is worth interrupting for, and it is the one
  direction that carries real value mid-flight. Status curiosity is not.
- **Every relay is REPORTED in the main session, as it happens.** Routing through
  the conductor is not enough on its own — if a finding passes from one lane to
  another and the user only learns of it from a merge commit, the coordination is
  invisible at the moment it mattered. State it in one line when it happens: which
  lane found what, which lane was told, and what changed in their instructions.

  This is not status chatter. A relay is the conductor CHANGING a lane's premise
  mid-flight, which is a decision — often one the user would have made differently.
  Concretely, these are worth a line each: a measurement that overturns a brief; a
  design change passed to a running lane; one lane's finding that invalidates
  another's approach; a lane correcting the conductor.

  The test: after the round, could the user reconstruct why each lane did what it
  did, without reading a transcript? If a lane's output only makes sense given a
  message it received, that message belonged in the main session.

- **Prevent overlap; do not detect it afterwards.** Anthropic's duplicate-work
  failure came from vague task descriptions — three subagents independently
  researching the same thing — and the fix was making responsibilities mutually
  exclusive in the prompt, before execution. A manifest is that, written down.
- **When a lane corrects the conductor, check it and say so plainly.** Briefs that
  say "I verified these facts myself; do not inherit my guesses — measure anything
  else" produce lanes that push back accurately, which is most of the value.

### A lane ESCALATES for a role; it does not seat one

A lane will hit things its own role cannot settle: a claim it cannot verify, a
design decision above its scope, code that wants a second read, a finding that
belongs to somebody else's territory. **It names the role it thinks is needed and
reports; the conductor decides whether to seat it.**

The lane must not spawn that role itself. Nesting is technically allowed, but a
role seated inside a lane is invisible to the conductor and to the user — it
breaks the same property as lane-to-lane messaging, one level down, and its
findings arrive folded into somebody else's report where they cannot be ranked.

**What a good escalation looks like** — the finding, the role, and why that role:

- *"`HuntAttemptWriter` has the same defect I just fixed, but it is main's code and
  not my lane's — this wants its own lane."* Became a rank-1 data-loss ticket.
- *"This control passed first time; I do not trust it."* → **skeptic**. The lane
  that said this found its own test was pinning nothing, and fixed it.
- *"The premise I was given is only true on an unmerged branch."* → back to the
  **conductor**, whose brief was wrong.
- *"Two tables now need one grain decision and I can only see one of them."* →
  **architect**, before either lane commits to a shape.

**The conductor answers every escalation explicitly**, in the main session, with
one of: seated (which role, which lane), folded into an existing lane, filed as a
ticket, or declined with a reason. An escalation that gets no answer teaches the
lane to stop raising them — and the next one will be the expensive one.

**Escalate the judgement, not the work.** "I need a skeptic on this claim" is an
escalation. "I could not get the build to pass" is a report, and the answer is
usually a better brief rather than another agent.

### Sequencing under a target

- **Do not dispatch two lanes whose outputs must agree.** Where one lane's answer
  determines another's shape — a design decision and the code that implements it —
  run them in series, and put the design first even when the code looks startable.
- **Design lanes parallelise cleanly with build lanes.** A lane producing a
  decision doc collides with nothing, so it is the safest way to keep width up
  while a schema or refactor lane holds a large surface.
- **A lane that must not touch something should be told so explicitly**, with the
  reason and the owner. "Do not edit any migration; V16 is reopened under #776 and
  another lane owns it" is worth more than a file list, because it survives the
  lane discovering a genuine reason to want it.

## Pick the executor, then write the brief

