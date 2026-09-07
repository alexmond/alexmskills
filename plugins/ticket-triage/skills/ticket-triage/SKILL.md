---
name: ticket-triage
description: >-
  Rank the open tickets, work out what is genuinely startable versus blocked, run
  the startable ones in parallel through to merged — then KEEP GOING: re-triage
  every time an agent finishes, so the backlog drains without being re-asked. Use
  for "what's next", "review tickets", "triage the backlog", "prioritise", "start
  in parallel", "drain the backlog", or a bare "go". Also takes a TARGET —
  "triage <target>", "work toward X", "drive the X epic" — which re-ranks by what
  unblocks that goal rather than by absolute severity, and coordinates lanes so
  they converge without colliding. Covers where the backlog lives, ranking,
  honest parallel width, briefing an agent so its result is trustworthy, and
  merging.
---

# ticket-triage

The recurring instruction is some form of *"review tickets, prioritise, start in
parallel."* This skill is the scheduler for that loop: it ranks, dispatches
isolated agents at an honest width, merges, and re-triages on every completion.
It schedules **across** tickets; what runs **within** a ticket is whatever the
ticket needs — a single role-briefed agent for most, a `dev-crew` relay for
multi-phase deliveries (see Composition).

## First run: the repo profile

Triage rules are portable; the facts they act on are not. On first run in a repo
(and on "re-profile"), write `.claude/ticket-triage/profile.md` by inspecting the
repo and asking the user only what can't be read:

- **Where the backlog lives** — the issue tracker, plus any doc-based roadmap or
  plan files that also hold pending work.
- **The verification command(s)** — the repo's real gate (test/lint/build), so
  briefs name it instead of inventing one.
- **Protected instances** — any running dev server/port that belongs to the user
  and must never be stopped, restarted, or measured against.
- **Merge policy** — squash vs merge, who merges (default: the conductor, never
  the agent), required checks.
- **Standing constraints** — decisions already made (ADRs, conventions) that
  briefs must state so they aren't re-litigated per ticket.

Read the profile at the start of every run. If `.claude/ticket-triage/`
doesn't exist, this is a first run.

## Start with the facts, not the ticket titles

```bash
bash <plugin>/scripts/backlog-snapshot.sh          # issues, PRs, worktrees, recent main CI
bash <plugin>/scripts/backlog-snapshot.sh --brief  # just issues + PRs
```

Read-only; it starts nothing and stops nothing. If the repo defines
`.claude/ticket-triage/snapshot-extra.sh`, the script runs it too — that is
where repo-specific facts (running instances, roadmap markers) come from.

**The backlog is usually more than one place, and the doc-based part drifts** —
in the direction that wastes the most time: items describing shipped work as
pending, or prescribing a measurement that can't answer its own question.
**Verify a doc-sourced item against the code before ranking it.** If it is
stale, fixing the doc is itself a ticket-sized piece of work worth doing.

## This is a LOOP, not a one-shot

Triage does not end when the agents are dispatched. **Every time an agent
finishes, run the same steps again** — so the backlog keeps draining without the
user re-asking.

### The cycle, on each completion

1. **Finish the finished one first.** Verify the load-bearing claims (see
   *Reports are evidence*), merge if green, delete the branch and its worktree,
   close the issue. **Before choosing the next ticket** — merging is what moves
   main and frees the files the next agent may need. Dispatching before merging
   is how two agents end up rebasing onto each other.
2. **Re-snapshot.** Never rank from a list taken an hour ago — merges close
   tickets, agents file new ones, and a research ticket can produce a blocker
   that outranks everything queued.
3. **Re-rank the whole open set**, not just the tail you remember. A finding
   ranks on its own merits the moment it lands, not queued behind the plan.
4. **Pick the top startable ticket** and check it against the skip list.
5. **Pick the executor, then dispatch** with a full brief, in **its own
   worktree** — or **skip** with one line saying why.
6. **Wait for the next completion.** No polling, no spinning, no starting
   something weaker just to be starting something.

### When to skip — start nothing, say why in one line

- **Blocked by an open dependency.** Blocked means blocked: N tickets that all
  need one definitional ticket first would otherwise produce N incompatible
  answers — the exact failure the foundation ticket exists to prevent.
- **Would collide on files with a running agent.** Partition by file *before*
  dispatch; if the top ticket wants a file a running agent owns, take the next
  ticket that doesn't, or wait.
- **Needs the user's decision** — irreversible (publishing, releasing) or
  preference. Never dispatch these; surface them separately.
- **Parked by decision** with a stated gate that hasn't fired. Re-check the
  gate rather than assuming — gates half-fire.
- **The ranking itself is uncertain** because an instrument is suspect. Fix the
  instrument first; it outranks the feature.
- **The queue is empty**, or everything left is one of the above.

A skip is a normal outcome, not a failure.

### When to stop looping

When **every** remaining item is parked, user-decision, or blocked: say so
**once**, list what would unblock the queue, and stop. Don't re-announce the
same standstill on every completion — that trains the user to ignore the
report. Resume when a merge, a decision, or a new ticket changes the set.

### What the loop must never do

- **Never widen scope to keep busy.** An empty queue is a result.
- **Never start something irreversible** because it was next in the ranking.
- **Never exceed the honest parallel width** just because agents are free.

## Ranking

In order:

1. **Data loss or a wrong answer presented confidently** — a pane claiming
   clean when the check failed, an action that silently doesn't act, a
   published artifact that cannot start. These outrank everything.
2. **Instrument defects.** A broken tool corrupts every judgement made through
   it, including this ranking — and a check that fails on things that are fine
   is also an instrument defect, because it trains people to ignore it.
3. **A blocking foundation** — the one ticket N others depend on. First makes
   the N cheap; last means N incompatible answers.
4. **Correctness the user can see** — wrong counts, dead links.
5. **Polish** — layout, truncation, contrast.

A priority label is an input, not the answer — labels are set at filing and
rarely revisited. Rank on what the ticket *says*, then reconcile with the
label. **Raise a label when you know something the filer could not** (e.g. the
broken module is one that publishes irreversibly), and say what you knew that
they did not, in a comment on the ticket, so the change is auditable.

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

## Parallel width is what is INDEPENDENT, not what is open

Rough scale, from Anthropic's published guidance and consistent with practice
here: a single fact-find is **one** agent; a comparison across a few dimensions is
**2-4**; genuinely complex work is **10+ but only with clearly divided
responsibilities**. Their early failure was spawning 50 agents for a simple query.
For repo work in worktrees, **3-5 concurrent lanes** is the band where the machine
and the merge queue both keep up.

The most common misjudgement. Nine open tickets does not mean nine agents.

- **Blocked means blocked** — see the skip list.
- **Partition by FILE before launching**, and tell each agent which files the
  others own. Ownership partitions *edits to existing files*; it must never
  stop an agent committing something new it built — a brief that reserves a
  directory says: commit your new script under a name nobody else holds, and
  send only the *documentation wording* for files someone else owns.
- **Give every agent its own worktree** (`isolation: "worktree"`). Not
  optional politeness: two agents in one checkout are one `git add -A` away
  from committing or destroying each other's half-finished work. A worktree
  costs ~200–500 ms and removes the entire class.
- **Scope git rules to the hazard.** In a shared checkout: never `-A`, `-a`,
  bare `stash`, `checkout .`, `clean`. In an isolated worktree the only rule is
  *stage what you meant to stage* — path-scoped stash/checkout are fine. A rule
  that fires where its reason doesn't apply trains agents to break stated
  rules.
- When an agent's work genuinely needs a file another owns, it **says so in its
  report** rather than editing it.
- **Say the width out loud and why.** "Two, because the other four are blocked
  by design" is a result; quietly starting two and not mentioning the rest is
  not.

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

### The conductor is a role too

Every role in `.claude/roles/` is SEATED — dispatched as a subagent with its own
context. The conductor is the one that is not: it is the role the MAIN session
adopts, and it is the lead in all four orchestrators (this skill, `dev-crew`,
`brainstorm-panel`, `research-sweep`).

Give it a `conductor.md` alongside the others. It earns the same charter / body /
learnings structure for the same reason they do — scheduling mistakes recur, and
today they have nowhere to accumulate: a lesson learned while running a crew does
not reach the triage loop, because skill-scoped learnings files do not see each
other. The recurring ones are about ASSERTING and MERGING, not about ranking.

Mark it non-seated in its "When to use", so tooling that assumes a role is
dispatched does not treat an unseated role as dead.

### The executor — generic is the fallback, not the default

- **A role from the shared substrate** (`.claude/roles/<role>.md`, seeded by
  the `roles` plugin) for single-agent tickets. **Choose the role from what the
  ticket IS, never from its area label**: a failure with no established cause
  is a `debugger` job; a choice between designs is an `architect` job; a
  too-clean claim gets a `skeptic`. The label says where the code lives; the
  role says what the work is. The payoff is the learning loop — a role file
  accumulates repo lessons a generic agent has nowhere to put.
- **A `dev-crew` relay** for multi-phase deliveries (design + implement +
  verify + release) — see Composition.
- **`general-purpose`** for work that is genuinely neither: filing tickets, a
  docs sweep, a measurement someone else will interpret. Say so when used.

Role-dispatch discipline (when the `roles` substrate is present):

- The brief tells the agent to **read the role file** (and seed it from the
  plugin if absent) — never merely name the role at it.
- **Seed the registry on main before dispatching** a round that needs roles
  `.claude/roles/` doesn't yet hold — otherwise every agent *creates* the file
  and they collide on merge.
- **One role file, one writer per round.** Name the owner in each brief; the
  others *report* their learning line so the conductor applies it.
- **Role files are repo state, so learnings belong in the PR.** A worktree
  agent that appends a learning and never commits it has thrown it away.
- Minting a new role needs a **stated gap** — one sentence naming work no
  existing role covers — and a line in the report saying a role was minted and
  why.

If the `roles` plugin isn't installed, dispatch generic agents with the same
briefs; everything else in this skill still applies.

### The brief

The brief is most of the quality. What repeatedly matters:

- **Four things, every time: objective, output format, which tools and sources to
  use, and clear boundaries.** Anthropic's lead agent failed exactly here — vague
  briefs produced subagents doing each other's work — and the fix was detail, not
  more agents.
- **Point at the issue and tell the agent to verify, not assume.**
- **Name the siblings and what they hold.** A lane that knows "another lane owns
  the migration, and a third is adding writers to the table your control counts"
  reports a collision instead of working around it silently. A file list alone
  does not carry this: the dangerous overlap is usually a shared *assertion*, not
  a shared line.
- **Say which of your facts came from an unmerged branch**, if any. A lane that
  measures and finds them absent has done the right thing, and should be told to
  say so rather than route around it.
- **Never hand over an unverified hypothesis as fact.** "I verified these
  facts myself; do not inherit my guesses — measure anything else you rely on"
  is the line that produces good work, and what lets an agent correct you
  cleanly. When a count feeds a brief, sanity-check the pattern against one
  known-positive instance before quoting it.
- **State the constraints that are already decided** (from the profile) so
  they aren't re-litigated per ticket.
- **Demand a control, not a green run.** A green test that has never been
  shown to fail pins nothing — ask for the mutation, the pre-fix rebuild, the
  positive control. A new check should assert **its own file is tracked** and
  that it scanned what it claims to scan; "it passed" and "it ran" are
  different facts.
- **Name the verification the repo already requires** (the profile's gate
  command), and the sweep rule: unrelated findings become issues, not scope
  creep.
- **Protect the user's instance** (from the profile): which port is theirs,
  that agents pick their own and stop it when done.
- Boilerplate every brief needs: the repo's commit/PR conventions; **do not
  merge — report back**.

## Reports are evidence, not gospel

Agents overturn claims — including the conductor's — and are also wrong.
Verify anything load-bearing yourself, **before merging**:

- A security change: read the diff.
- A claimed fix to a broken artifact: **run the artifact.**
- A claimed control: **re-run it** against the pre-fix state.
- A surprising negative deserves the same scrutiny as a surprising positive.
- **When two agents disagree, go to the code** — never average them, and say
  plainly which was right.
- When an agent corrects *you*, check it and then say so plainly.

## Merging and cleaning up

- Wait for mergeability honestly: an unknown/pending state means GitHub hasn't
  computed or checks are still running — re-check, don't conclude.
- **Check the PR's file list against what the agent said it changed** — one
  command, and it catches another agent's work swept into the branch.
- **Merge order matters** when two PRs touch the same file (learning logs and
  CLAUDE.md are the usual collisions). Merge, let the next agent rebase.
- **After merging, check main's run, not just the PR's** — a branch green
  before the merge is not evidence about the commit the merge created.
- After each merge: remove the **finished** agent's worktree and branch —
  but first **ask what is in the worktree that is not in the PR** (an agent
  may have built an instrument it was told not to commit into someone else's
  directory). Leave running agents' worktrees alone.
- **Never `git pull` the shared checkout while an agent works in it.** Read
  merged content with `git show origin/main:<path>` in the meantime; grepping
  a deliberately-stale working copy produces confident wrong conclusions.
- Restart the user's instance when merges made it stale — saying so, never
  silently.

## Report back in the shape that is useful

A table of what merged and what it found, the corrections (yours included),
what is still blocked and why, and — kept separate — **what needs the user's
decision**. Irreversible and preference calls are theirs; burying them in a
status list is how they get missed. In loop mode keep the per-completion
report **short**: what merged, what it found, what started next. Save the full
shape for a round that ends or a finding that changes the plan.

## Composition

- **`dev-crew`** (this marketplace) runs one relay-worthy ticket through its
  gated phases. Triage schedules across tickets; the crew executes within one.
  Each relay runs in the ticket's worktree — the crew's run state is untracked
  and CWD-relative, so parallel relays isolate for free.
- **Cross-session/cross-repo work** hands off through the issue tracker
  itself: file the ticket in the other repo, monitor it to resolution, and
  treat the reply as a completion event in this loop.
- **The `roles` plugin** supplies the persona substrate and the learning loop
  the dispatch discipline above assumes.

All three are optional; triage degrades to generic agents and a single repo.

## Learning loop

The rules above were earned; keep earning them. When a run misjudges a
priority, a dependency, or the width — or an agent surfaces a gotcha the brief
should have carried — append a dated line to
`.claude/ticket-triage/learnings.md` in the consuming repo (the installed
plugin is a read-only cache):

```
- YYYY-MM-DD — what happened → what changed.
```

Read that file at the start of every run, right after the profile. A learning
that recurs across repos is a candidate to upstream into this skill.
