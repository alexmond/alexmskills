# competitive-review log

**Read-only seed.** On first run in a repo, copy this file to `<repo>/.claude/competitive-review/log.md`
and append there. Never write to the installed copy — a marketplace-installed plugin lives in a
read-only cache.

Evidence from each review, so the next one in this category starts smarter. Graduate stable findings
into the repo's `CLAUDE.md` under `## Competitive review`, then prune them from here — this file is
evidence, not history.

## Entry schema

```markdown
## YYYY-MM-DD — <subject>, <mode>

- **Category:** <the space as scoped>
- **Hypotheses:** H1 <claim> → confirmed | falsified | refined. H2 …
  (the falsifications are the payload — record what replaced the claim)
- **Partition:** <axis chosen>, <n> slices. Thin: <slice> — slice-thin | agent-thin, <action taken>.
- **Verifier findings:** <sample size>; <fabrications>; <duplicates at which seam>; <what was missing>.
- **Liveness surprises:** <projects whose apparent state was wrong, and the trap that hid it>.
- **Steering:** <what the user changed at the hypothesis gate — the strongest signal here>.
- **Outcome:** <what the review changed: positioning, roadmap, a killed assumption>.
```

## What is worth logging

- A hypothesis that came back **falsified**, and the sharper claim that replaced it.
- A partition axis that carved this category cleanly — or badly, and why.
- A liveness trap that nearly produced a wrong entry.
- What the user changed at the hypothesis gate. An added hypothesis means the framing missed
  something the subject cares about; a cut one means the default over-reaches here.

Do not log routine outcomes. A run where everything worked needs one line.
