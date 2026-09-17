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

## Load evidence — what actually loaded, not what should have

`record-loads.py` runs on `InstructionsLoaded` and appends one line per event
to `.claude/evolving-claude-md/loads.jsonl` (rolling window, not an archive):
which instruction file loaded, in which session, and the `load_reason`
(`session_start`, `nested_traversal`, `path_glob_match`, `include`, `compact`).

Every other check here reasons about what the file *says*. Two failures are
invisible to all of them, and both show up only as a missing load event:

- **A dead rule.** A `.claude/rules/*.md` whose `paths:` globs never match
  anything that gets read is perfectly well-written and never consulted. No
  content audit can flag it, because the content is fine.
- **An instruction file that never loads.** Claude Code loads a `CLAUDE.md` up
  to 4 MiB and silently *skips* a larger one; a file in a path the client
  doesn't read is skipped just as quietly. The repo looks configured and isn't.

Both accusations wait for `load_min_sessions` (default 5) of recorded evidence,
because "it hasn't loaded yet" and "it never loads" look identical on day one.

## Why supersede links, and where they came from

Borrowed from temporal knowledge graphs, where invalidating a fact records
*when* it stopped being true instead of leaving both versions standing. Of 80
instruction-upkeep tools surveyed, half document no staleness handling at all,
and that was the one mechanism worth copying.

## Merging same-session clusters (full rule)

### 2. Merge same-session clusters (the pre-14-days lever)
When a single work session lands 4+ entries about one piece of work — phased rollouts (`e2a-web`, `e2b-db`, `e3-consume`), same-feature aspects (`diff` + `diff-absolute`), bursts dated within ~48 hours of one another on the same area — **collapse them into one consolidated entry** with a single broader topic-tag. The compressed body keeps the load-bearing whys; the per-aspect detail moves to `docs/decisions/{date}-{topic}.md` if it's still wanted.

This is the *only* compaction action that works pre-14-days. Graduation requires 14-day stability (so a stable pattern hasn't proven itself yet); archive requires a date cutoff older than entries. When the audit fires "Compaction RECOMMENDED" but every entry is young, merge is what's left.

Triggers for merging:
- Multiple entries dated within ~48h on the same broad area (the topic-tags read as a numbered sequence, or as facets of one effort)
- The audit's mega-entry list is empty (no single entry is too big) but the *count* is over threshold
- Reviewing the cluster, the consolidated version reads at least as well as the spread

Merge does NOT graduate — the result is still in Decisions & Learnings, not Conventions. Reversibility: if a sub-decision later evolves independently, split it back out as a new entry that strikes through the consolidated one with a follow-up.
