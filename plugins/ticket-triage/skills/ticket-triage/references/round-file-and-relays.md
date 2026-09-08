# The round file, echoes, and the relay log

Three failures that share one cause: **a round leaves no trace outside the
conductor's context.** All three were measured in a single session.

## Why a file, not a memory

`profile.md` holds facts and `learnings.md` holds lessons. Neither records that
a round is IN FLIGHT — the ranking, the dispatched lanes, the next candidate. So
the loop lives only in the conductor's context, and one compaction reduces it to
a sentence in a summary ("the next iteration would re-rank the open set"): a
description of an intention, not a resumable record. `dev-crew` has run-dir
state; triage had none, and the loop died silently after a round merged with
neither party able to see that it had.

## `.claude/ticket-triage/round.md`

Written at dispatch, updated on every merge and every relay, deleted when the
queue empties. Keep it mechanical — it is read by a future conductor who has
lost the context, and by the user.

```markdown
# Round <n> — started <ISO date>, target: <goal or "backlog drain">

## Ranked set (as of <ISO date>)
1. #743  p1  rehearse V16 on all three deployments      DISPATCHED  lane a47f…
2. #783  p1  port the site-photo quarantine pair        DISPATCHED  lane a4e5…
3. #784  p1  port the catalog-seed triage chain         next
4. #766  p2  surrogate keys                             blocked by #776

## Lanes
| lane | ticket | ROLE | owns | verification | state |
|---|---|---|---|---|---|
| a47f… | #743 | skeptic | `tools-workflows/` | test-affected | running |
| a4e5… | #783 | step-porter | `tools-steps/` | test-affected | merged 19:14 |

## Relays  (append AT SEND, never after)
- 19:02  a47f…  correction  my V16 layout is wrong: Flyway scans recursively
- 19:20  a4e5…  owner call  "go straight to option 2" — stop converging schema
```

The state column is what makes an echo detectable, and the relay log is what
makes the reporting rule mechanical instead of remembered.

## Echoes: a completion can re-fire

A completion notification can arrive hours late, carrying the lane's own stale
self-report — *"not merged, not pushed"*, true when written and false on
arrival. Five merged lanes produced ~10 such re-fires. Step 1 of the cycle
followed literally would re-merge already-merged branches.

**Check the task-id against the round file and `git branch --merged main`
before acting.** Never take a lane's account of its own merge state: the
conductor merges, so the lane structurally cannot know. This is distinct from
"reports are evidence, not gospel" — that section is about a lane's *findings*;
this is about its report on its own lifecycle.

## Relays: verifying one actually landed

`SendMessage` returns:

```json
{"success": true, "message": "Message queued for delivery to <id> at its next tool boundary"}
```

**That acknowledges QUEUING, not receipt.** A lane that has finished or been
killed never reaches another tool boundary, so `success:true` is not evidence of
delivery and must never be reported as such.

The receiving side is the evidence. A relay lands in the lane's own transcript
at `~/.claude/projects/<encoded-cwd>/<session>/subagents/agent-<id>.jsonl` as a
**`type=attachment`** entry — *not* a `role=user` turn.

Match it by **exact normalised 50-char substring taken at three independent
offsets**. Two cheaper methods were measured and both lied:

| method | verdict | why it was wrong |
|---|---|---|
| 60-char probe at one fixed offset | 38/76 — "half missing" | the offset landed on `**` and em-dashes that normalise differently |
| rare-word overlap ≥ 60% | 76/76 | right by luck — shared jargon satisfies it; would pass a message never sent |
| exact 50-char at 3 offsets | **76/76** | reuse this one |

A role-based scan reading `content[].type=="text"` also said "2 of 12 arrived",
also wrong — relays are attachments, not text turns.

**Delivery is not action.** Confirm action separately from the lane's own
output: the lane told *"take option (b)"* opened its final report with *"The
design decision: option (b)"*.

## Why the reporting rule needs a method

SKILL.md requires reporting every relay in the main session, because a relay is
a decision the user should not learn of from a merge commit. Measured against
one session: **76 relays sent, 0 surfaced.** By kind — 20 telling a lane a given
premise had changed, 17 correcting a conductor error, 4 relaying an owner
decision verbatim, 4 lifecycle, 2 scope kills, 29 progress. **47 of 76 were
decisions the rule names explicitly.**

The cause is structural, not forgetfulness: a `SendMessage` result returns to the
*conductor*, never to the user, so the only surface a relay can reach is the
conductor's own prose — and relays are sent *between* user-facing turns, while
processing a lane report. By the time a turn is written, the relay is process
rather than result and does not survive into the summary.

A rule that depends on narrating a tool call you made three calls ago will break
every time the round is busy, which is exactly when relays happen. Hence: log at
send, render what is new in each report.

## Starting or continuing from the round file

A session that finds `round.md` is joining a round in flight, not starting one.

**Adopt rather than re-derive.** Take its target, its ranked groups and its blocked list as
given. Re-ranking from scratch discards the previous session's grounding work and risks
re-dispatching a ticket that has already merged.

**Verify only what can have changed since:**

- the lanes it names, against `git branch --merged main` — a lane's own report of its merge
  state is the one claim never to trust, because the conductor merges and the lane cannot know;
- whether any ticket it ranks has since closed;
- whether an owner-decision it flagged has been answered.

**Then say in one line what you adopted** — target, next candidate, and anything you found
already done. The user should be able to see the plan survived the session boundary without
reading the file themselves.

**Delete it when the queue empties**, so its presence always means "a round is live".

### Why the ROLE column is not decoration

The role is chosen from what the ticket IS, never from its area label — a failure with no
established cause is a `debugger` job, a choice between designs an `architect` job, a
too-clean claim a `skeptic`. That makes it a **reviewable decision**: a later reader can ask
whether it was the right seat, and the roster's accumulated learnings can be traced back to
the runs that produced them. A table of tickets alone cannot answer *"why was a skeptic
seated here"* — and when a lane returns a surprising verdict, the role it was given is
usually half the explanation.
