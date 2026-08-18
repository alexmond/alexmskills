---
name: skill-linter
description: Audit SKILL.md files against published skill-authoring guidance — frontmatter validity, whether the description actually says when to trigger, body size, progressive disclosure, and broken references. Use when the user says "lint my skills", "check my SKILL.md", "review this skill", "do my skills conform", "audit the marketplace", or is about to publish, rename, or graduate a skill. Use proactively right after writing or editing any SKILL.md, and whenever a skill turns out not to trigger when it should have. Self-learning — a defect it failed to catch becomes a new rule.
---

# skill-linter

Checks the *form* of a skill. Whether a skill actually works is a different and
much more expensive question — that belongs to `skill-creator`'s eval loop, which
runs the skill against real prompts with and without it. This exists so that loop
is never spent on a typo in the frontmatter.

Being honest about that boundary matters, because the failure mode here is a
green lint being mistaken for a working skill. It is not. It means nothing
mechanical is wrong.

## What it lints

`SKILL.md` files, and — since 0.2.0 — `agents/*.md`. Agents earned their slot the
hard way: three shipped "read-only" agents used `allowed-tools:` (the
slash-command field, silently ignored in agents) and ran with the full tool set
for months. `agent-wrong-tools-field` is an *error* for that reason: it is not a
style problem, it is a false safety claim.

## Run it

```bash
python3 <plugin>/scripts/lint_skills.py plugins        # a tree
python3 <plugin>/scripts/lint_skills.py path/to/skill  # one skill
python3 <plugin>/scripts/lint_skills.py . --strict     # gate: any finding fails
python3 <plugin>/scripts/lint_skills.py . --json       # for tooling
```

Exit 0 clean, 1 on any error, and with `--strict`, 1 on anything at all — so it
drops into CI or a pre-commit hook unchanged.

Findings come in three levels, and the split is deliberate: **error** means the
skill is broken as a skill (it cannot be loaded or addressed), **warn** means it
will load but underperform, **info** is a style note worth a look but not worth
blocking on.

## The rules and where they come from

Every rule traces to published guidance, cited per-rule in
[references/rule-sources.md](references/rule-sources.md). Read that file before
adding, changing, or arguing with a rule — it also records the two places where
the sources contradict each other and how each is resolved.

The rules that matter most, in rough order of how much damage they do:

| Rule | Why it earns a place |
|---|---|
| `frontmatter-invalid` · `name-mismatch` | The loader keys off the directory and the frontmatter. Get either wrong and the skill is unreachable — no amount of good content compensates. |
| `description-no-trigger` | The description is the *only* thing read when deciding whether to load a skill. One that never says when it applies is a skill that quietly never fires. |
| `trigger-info-in-body` | A `## When to use` section in the body cannot influence a decision that was made before the body was read. |
| `description-recites-workflow` | Steps in the description become a shortcut. An agent that can read the workflow there may act on it and never open the skill. |
| `description-first-person` | Descriptions are injected into a system prompt, where "I can help you…" reads as the wrong speaker. |
| `body-too-long` | The whole body loads on every trigger. Past ~500 lines that is a real tax, and the fix — move detail into `references/` and point at it — costs nothing. |
| `broken-reference` · `force-loading-link` | A pointer to a missing file wastes a turn; an `@`-link spends context before the skill knows it needs it. |

Two guards keep the output trustworthy, and both exist because the first run
produced false positives:

- **Fenced code is not prose.** Skills demonstrate bad patterns on purpose and
  embed templates whose filenames do not exist yet. Content rules read the body
  with fences blanked out.
- **Quoted phrases are the user's voice.** A description *should* quote what
  people type, and people say "lint my skills". Person checks skip quoted spans.

## Reading a result

Report findings grouped by skill, worst level first, and lead with the reasoning
rather than the rule id — an author who understands why a rule exists will fix
the underlying problem instead of the symptom. Say what to change, not just what
is wrong.

When the run is clean, say so plainly and name the boundary: the form is sound,
the behaviour is untested.

## Fixing what it finds

Offer to fix, then fix — most findings are a one-line edit to the description.
Two are not, and both deserve a conversation first:

- `body-too-long` means deciding *which* sections become references, which is a
  judgment call about what a reader needs on every invocation.
- `description-no-trigger` on a skill that is dispatched by name rather than by
  matching is arguably correct as-is. Confirm the intent before "fixing" it — but
  weigh it against the cost, since every skill's description sits in context for
  every session whether or not it can ever fire.

After editing any description, re-run the linter on that skill. Descriptions are
easy to overcorrect: adding trigger phrases often introduces the second-person
voice the next rule objects to.

## Learning loop

The linter is meant to get sharper with use. Two things trigger a change, and
both come from the same source — evidence that the current rules were wrong.

**A miss.** A skill defect surfaces that a lint should have caught: a skill that
never triggered, a reference nobody could open, a description that sent an agent
down the wrong path. Record the rule that would have caught it.

**A false positive.** A finding is dismissed as not a real problem. That is
equally valuable and more urgent, because a noisy linter gets ignored wholesale.
Narrow the rule or disable it.

Both are written to the **consuming repo**, never to the plugin directory — an
installed plugin lives in a read-only cache:

```
.claude/skill-linter/
├── learned-rules.json   # new rules, applied automatically on the next run
└── log.md               # dated misses, false positives, and what changed
```

A learned rule is data the checker executes, so a lesson takes effect immediately
without editing any code:

```json
{
  "rules": [
    {
      "id": "no-bare-tool-list",
      "scope": "description",
      "pattern": "\\b(Read|Write|Bash|Grep)(,\\s*\\w+){2,}",
      "absent": false,
      "severity": "warn",
      "message": "description lists tool names instead of situations",
      "why": "a user asking for help does not name the tools; matching on them misses the real prompt",
      "source": "miss on 2026-08-08, repo: alexmskills"
    }
  ]
}
```

`scope` is `description`, `body`, `name`, or `all`. Set `absent: true` to fire
when the pattern is *missing* rather than present. Set `"enabled": false` to
retire a rule without losing the record of why it existed.

Every entry needs the `why` and the `source`. A rule whose reasoning was never
written down cannot be re-litigated later, and a rule that cannot be
re-litigated eventually gets ignored instead of fixed.

**Graduation.** A learned rule that has fired correctly across several repos and
has never been dismissed has earned its way into the shipped checker — move it
into `check()` in `scripts/lint_skills.py`, add a case to the harness, and delete
it from `learned-rules.json`. Shipped rules are code precisely so they are
reviewable in a diff and covered by tests; learned rules are data so a lesson can
be captured the moment it is learned. Keeping that boundary is what stops the
JSON file from silently becoming the real linter.

Note both directions in `log.md` with a date, the evidence, and the change — that
log is what makes a rule defensible six months on.

## Extending the checker

New shipped rules go in `check()`. Match the existing shape: cite the source in a
comment, pick the level by how much damage the defect does, and write the hint as
an explanation rather than an instruction.

Add a harness case for anything new, and add a *negative* case alongside it. The
harness deliberately spends half its checks asserting that things do **not**
fire, because a linter's credibility is destroyed by noise long before it is
destroyed by a missed defect.

```bash
python3 <plugin>/scripts/test-harness.py    # or: make test-linter
```

The harness ends by running the linter against this skill's own SKILL.md and
requiring it to come back clean. If the bar cannot be met by the file that sets
it, the bar is wrong.
