# Audit checks in detail

The reasoning behind two checks whose SKILL.md entries are summaries: the
upward coverage check and the structure review.

## Coverage — the one upward check

Every other check pushes content *down*: bloat, staleness, clustering, archiving. A
file can pass all of them and still be useless — well under every threshold,
perfectly formatted, and never saying how to run the tests. Coverage is the check
that asks whether the essentials are there at all.

Two gaps, both **grounded in the tree rather than in a checklist**:

| Gap | Fires only when |
|---|---|
| *no build/test command* | a build file exists (`pom.xml`, `package.json`, `Cargo.toml`, `go.mod`, `Makefile`, … — 12 supported) **and** CLAUDE.md never mentions its command |
| *nothing on layout* | the repo has 5+ meaningful top-level directories (generated ones like `target/`, `node_modules/` don't count) **and** CLAUDE.md never describes where anything lives |

Grounding is the whole design. A docs repo has no build command, and a
three-directory repo needs no layout section — a generic checklist nags both. On a
29-repo sample these two fired **zero** times, because every one of those repos
already covers what its tree justifies.

To decline a gap permanently, put the decision in the file itself:

```markdown
<!-- audit-skip: commands, layout -->
```

**Deliberately not checked: a "gotchas" section.** Measured on the same 29 repos it
fired on 17 (59%) — noise, not signal. Worse, those 17 were exactly the repos with
no D&L log, so it was only re-detecting "hasn't adopted this skill", which the audit
already says. Gotchas arrive by *graduation* from the log; the topic-cluster check is
the grounded way to prompt for them. Don't re-add it without data.

## Structure review — evolve the file's shape, not just its entries

The file's *internal structure* rots with the project: sections outlive their
subject, content sits at the wrong level, layout prose stops matching the
tree. Run a structure review when the user asks ("review CLAUDE.md
structure"), when drift/adoption states fire, or during a compaction pass:

1. **Ground in the rulebook** —
   [references/claude-md-best-practices.md](references/claude-md-best-practices.md),
   the researched, cited practices. Every recommendation must trace to a rule
   there or to a tree-provable audit state. No invented taste.
2. **Inventory the file** — sections, sizes, content classes, current flags.
3. **Recommend, don't rewrite** — adds / moves / removals as a short list,
   each with its citation and destination (inline, `docs/`, `.claude/rules/`,
   a skill, user memory, deletion). The user picks; apply what they accept.
4. **Respect the measured hierarchy** — presence, brevity, and consistency
   dominate; reordering is mostly noise (see the rulebook's "what NOT to
   optimize"). Prefer deletions and relocations over rearrangements.
