---
name: ticket-triage
description: >
  Rank the open tickets, work out what is genuinely startable versus blocked, run the startable ones in parallel through to merged — then KEEP GOING: re-triage every time an agent finishes. Use for "what's next", "review tickets", "triage the backlog", "prioritise", "start in parallel", "drain the backlog", or a bare "go". Also takes a TARGET — "triage <target>", "work toward X", "drive the X epic" — re-ranking by what unblocks that goal and coordinating lanes so they converge without colliding.
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

**START BY READING `.claude/ticket-triage/round.md`.** If it exists, a round is in
flight: adopt its target, its ranking and its blocked list rather than re-deriving them,
verify the lanes it names against `git branch --merged main`, and continue from its next
candidate. Re-ranking from scratch over a live round wastes the previous session's work and
risks re-dispatching finished tickets. **The file is the state of the loop, not a log.**
Say in one line what you adopted, so the user can see the plan survived.

**And write it.** `.claude/ticket-triage/round.md`, at dispatch — the ranked set, each lane with its ticket and branch, the next
candidate, and a relay log — update it on every merge and every relay, delete it
when the queue empties. Without it the loop lives only in the conductor's
context, and one compaction reduces it to prose about an intention; nobody, the
user included, can then answer "is the loop still running?" by looking.
→ `references/round-file-and-relays.md`.

### The cycle, on each completion

1. **Finish the finished one first — after checking it is not an ECHO.** A
   completion can re-fire hours later carrying the lane's own stale self-report
   ("not merged, not pushed"), true when written and false on arrival. Check the
   task-id against the round file and `git branch --merged main`; never take a
   lane's account of its own merge state, since the conductor merges and the
   lane cannot know. Then verify the load-bearing claims (see
   *Reports are evidence*), merge if green, delete the branch and its worktree,
   close the issue. **Before choosing the next ticket** — merging is what moves
   main and frees the files the next agent may need. Dispatching before merging
   is how two agents end up rebasing onto each other.
2. **Re-snapshot.** Never rank from an hour-old list — merges close tickets, agents file
   new ones, and a research ticket can produce a blocker that outranks the queue.
3. **Re-rank the whole open set.** A finding ranks on its own merits the moment it lands,
   not queued behind the plan.
4. **Re-check the RUNNING lanes, then pick.** A merge moves `main` underneath them, and a
   lane that overturned its own brief is no longer doing what its partition describes —
   re-verify each one's premise and ownership and RE-ARRANGE (relay, narrow, or stop)
   rather than discovering the overlap at merge. Then pick the top startable ticket and
   check it against the skip list.
5. **Pick the executor, then dispatch** with a full brief, in **its own
   worktree** — or **skip** with one line saying why.
6. **Wait for the next completion.** No polling, no spinning, no starting
   something weaker just to be starting something. **An operator question
   SUSPENDS the loop; it does not end it** — answer it, then return to step 2
   and say in one line what was dispatched, or why nothing was.

### When to skip — start nothing, say why in one line

- **Blocked by an open dependency.** N tickets needing one definitional ticket first would
  otherwise produce N incompatible answers — the failure the foundation ticket prevents.
- **Would collide with a running lane** — by file, or by shared assertion. Partition
  before dispatch and RE-CHECK it after every merge; take the next ticket, or wait.
- **Needs the user's decision** — irreversible (publishing, releasing) or
  preference. Never dispatch these; surface them separately.
- **Parked by decision** with a stated gate that hasn't fired. Re-check the
  gate rather than assuming — gates half-fire.
- **The ranking itself is uncertain** because an instrument is suspect. Fix the
  instrument first; it outranks the feature.
- **The queue is empty**, or everything left is one of the above.

A skip is a normal outcome.

### When to stop looping

When **every** remaining item is parked, user-decision, or blocked: say so **once**, list
what would unblock the queue, and stop. Re-announcing the same standstill trains the user
to ignore the report. Resume when a merge, a decision or a new ticket changes the set.

### What the loop must never do

- **Never widen scope to keep busy.** An empty queue is a result.
- **Never start something irreversible** because it was next.
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

`triage <target>` is the same loop with a different ranking key — a goal, not a
ticket. **A ticket that BLOCKS the target outranks its own label; a rank-1 defect
still preempts anyway.** Name the blockers before dispatching (a target with no
stated blocker list is a wish), expect to file as you go, say what the target does
NOT include, and stop when the goal moves rather than when the backlog empties.

## Lanes that can see each other

File partitioning stops two lanes editing one line. It does not stop **two lanes
making claims about a tree that only exists after both merge** — a control and the
thing it counts, a lane reasoning from another's unmerged branch, one lane moving
code out from under another.

- **Findings flow lane → conductor → lane, never lane → lane.** Two lanes agreeing
  directly produce an arrangement you then merge and cannot explain.
- **Partition by what will COLLIDE, not what will be edited.** The dangerous
  overlap is a shared *assertion* — a test asserting an exact set — not a shared
  line. Never weaken set equality to a subset check to make a merge pass.
- **The round file's LANES table names the ROLE, not just the ticket.** The role is the
  reviewable decision — a table of tickets cannot answer "why was a skeptic seated here".
- **The conductor messages a running lane when a premise it was GIVEN has
  changed**, and reports every such relay in the main session: a relay is a
  decision, and the user should not learn of it from a merge commit. **Log it AT
  SEND** — one round-file line per `SendMessage` — and render the new lines in
  each report. A rule that depends on narrating a tool call you made three calls
  ago breaks exactly when the round is busy, which is when relays happen: 76
  sent in one session, 47 of them decisions, and the user saw none.
- **A lane ESCALATES for a role; it does not seat one.** It names the role it
  needs — skeptic, architect, reviewer — and reports. Seating is the conductor's
  call, answered explicitly: seated, folded, filed, or declined with a reason.
- **Lanes whose outputs must agree run in SERIES, design first.** Design lanes
  parallelise cleanly with build lanes.

→ `references/targeted-runs-and-lanes.md` for the observed failure shapes, the
manifest, and worked escalations.

### The conductor is a role too

Every role in `.claude/roles/` is SEATED as a subagent. The conductor is the one that is
not — it is the role the MAIN session adopts, and it is the lead in all four orchestrators.
Give it a `conductor.md` alongside the others, marked non-seated: scheduling mistakes recur
and today have nowhere to accumulate. → `references/role-dispatch.md`.

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

Role-dispatch discipline when the `roles` substrate is present — read the role
file rather than naming it, seed the registry on main before the round, one
writer per role file, learnings belong in the PR, and a mint needs a stated gap:
→ `references/role-dispatch.md`.

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
- **Never hand over an unverified hypothesis as fact.** "I verified these facts myself;
  do not inherit my guesses — measure anything else you rely on" is what lets an agent
  correct you cleanly, and they will: **a stale premise is the most expensive brief defect
  there is**, because the lane trusts it and builds before discovering it.
- **State the constraints that are already decided** (from the profile) so
  they aren't re-litigated per ticket.
- **Demand a control, not a green run.** A green test never shown to fail pins nothing —
  ask for the mutation or the pre-fix red. A new check must assert its own file is tracked
  and that it scanned what it claims to; "it passed" and "it ran" are different facts.
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

- **`dev-crew`** runs one relay-worthy ticket through its gated phases; triage schedules
  ACROSS tickets, the crew executes WITHIN one. Each relay runs in the ticket's worktree —
  crew run state is untracked and CWD-relative, so parallel relays isolate for free.
- **Cross-repo work** hands off through the issue tracker: file it there, monitor to
  resolution, treat the reply as a completion event in this loop.
- **The `roles` plugin** supplies the persona substrate the dispatch discipline assumes.

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
