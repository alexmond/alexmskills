# CLAUDE.md best practices — the researched rulebook

The evidence base for this plugin's **structure review** (see SKILL.md). Every
rule cites its source; a recommendation that can't point at a rule here or a
tree-provable audit check doesn't get made. Compiled 2026-08-28 by a
three-scout research sweep (official Anthropic guidance / real committed
files in notable repos / practitioner writing), 96 findings, 12-sample
adversarial verification with zero fabrications. Raw findings with full
evidence text live in the sweep's findings YAML in the source repo.

Sources are tiered — when they disagree (they do, and the disagreements are
listed), weigh **measured > official > observed > opined**.

## 1. What belongs in the file

- **Facts needed in every session**: build/test commands, conventions, layout,
  "always do X" rules. Multi-step procedures and part-of-codebase content go
  to a skill or path-scoped rule instead.
  [official — code.claude.com/docs/en/memory]
- **The include list**: bash commands Claude can't guess; style rules that
  differ from defaults; testing instructions and preferred runners; repo
  etiquette (branch/PR conventions); project-specific architecture decisions;
  environment quirks; gotchas.
  [official — code.claude.com/docs/en/best-practices]
- **Exact commands are the most universal real-world content class**, often
  annotated with cost warnings ("Do not run pytest by itself; it'll take
  forever!") and always including the *run-one-test* invocation as its own
  line. [observed — sentry, ghostty, deno, anthropics/claude-agent-sdk-python]
- **Name your tools.** Tools mentioned in the file get used ~160× more than
  unmentioned ones — the single highest-leverage content decision.
  [measured — philschmid.de/writing-good-agents]
- **Deltas, not defaults**: several exemplar files scope themselves to "where
  this repo differs from your defaults" and tell the agent that adjacent code
  beats written rules. [observed — twenty, temporal, bun]
- **Red lines are their own class**: a few unconditional NEVERs (secrets,
  customer data, security-sensitive paths), phrased distinctly from style
  guidance. [observed — sentry, codex, uv]

## 2. What does NOT belong

- Anything Claude can derive from the tree: directory listings, dependency
  lists, architecture overviews, file-by-file descriptions.
  [official — /doctor trim criteria, code.claude.com/docs/en/memory;
  corroborated by philschmid.de]
- Standard language conventions, detailed API docs (link instead),
  fast-changing information, tutorials, "write clean code" truisms.
  [official — code.claude.com/docs/en/best-practices]
- Style enforcement — "never send an LLM to do a linter's job"; hard
  constraints belong in hooks/linters/CI, because CLAUDE.md is advisory
  context, not enforced configuration.
  [opined — humanlayer.dev; official — memory docs "context, not enforced
  configuration"]
- The per-line test: **"would removing this cause Claude to make mistakes?"
  If not, cut it.** [official — code.claude.com/docs/en/best-practices]

## 3. Size

- Official target: **under 200 lines** per file; hard load cap 4 MiB; shorter
  files produce better adherence. [official — memory docs]
- Practitioner consensus: **under 300 lines**, with good production files
  under 60; framing is an *instruction budget* (~150–200 instructions
  followed reliably, ~50 already spent by the harness), not a token budget.
  [opined — humanlayer.dev]
- The measured caveat: a 1,650-session study found file length (25–500 lines)
  produced **no detectable compliance difference** — but *having* a file
  mattered enormously (a rule was followed 0/524 times without one), and
  compliance decays within a session either way.
  [measured — arXiv 2605.10039; alexdunlop.com]
- Observed reality: mature projects land between 100–350 lines; the visible
  failure mode is a 700-line/120 KB append-only accretion file.
  [observed — size band across ~30 top repos; OpenHands anti-pattern]

## 4. Content separation — the ladder

Where content goes when it leaves the root file, in order of preference:

1. **Delete** — if it fails the per-line test. [official]
2. **`.claude/rules/` path-scoped files** — one topic per file; `paths`
   frontmatter defers loading until matching files are touched. This is the
   ONLY split that actually saves context: `@imports` still load at launch.
   [official — memory docs, twice]
3. **Skills** — domain knowledge and sometimes-relevant workflows, loaded on
   demand. Exemplars index them with one-line pointers.
   [official — best-practices; observed — next.js `$flags` skills, sentry]
4. **Nested per-directory CLAUDE.md** — loads on demand when files there are
   read; the two-level split (root = everywhere-rules, subdir = stack
   conventions) is the prescribed monorepo shape. Root file can be a router
   mapping globs to files. [official — large-codebases; observed — bun (10
   files), sentry "Context-Aware Loading"]
5. **Link out to existing docs** — don't restate contributor docs; the agent
   file is environment facts plus pointers. Counter-lore: linked files are
   not reliably followed — conditional phrasing ("When adding CSS, refer to
   docs/ADDING_CSS.md") pierces better than bare links.
   [observed — angular, vscode; opined — HN threads, both directions]
6. **User memory / CLAUDE.local.md** — personal, machine-specific, private.
   Gitignored local file, or an imported home-directory file for worktrees.
   [official — memory docs]
- **AGENTS.md interop**: the dominant large-OSS pattern is a canonical
  AGENTS.md with CLAUDE.md as a symlink or one-line `@AGENTS.md` stub.
  [observed — airflow, next.js, ruff, uv, sentry, rust-lang + 6 more]

## 5. Structure

- Markdown headers + bullets grouping related instructions; no required
  format. A pure headingless NEVER/ALWAYS rule list is a viable minimal form.
  [official — memory docs, best-practices; observed — uv]
- **Concrete enough to verify**: "Use 2-space indentation", never "Format
  code properly". One real code snippet beats three paragraphs of prose.
  [official — memory docs; measured — GitHub 2,500-repo analysis]
- **Emphasis is a scarce resource**: reserve IMPORTANT/NEVER for the one rule
  being skipped; exemplar files use single-digit CAPS counts even at 500
  lines. [official — best-practices; observed — emphasis survey]
- Effective files front-load executable commands and carry three-tier
  boundaries (always / ask first / never).
  [measured — GitHub 2,500-repo analysis]
- Block-level HTML comments are stripped before injection — maintainer notes
  are free. [official — memory docs]

## 6. Evolution and maintenance

- **Add on trigger, not ambition**: a repeated mistake, a review catch, a
  re-typed correction — "Claude gets a convention wrong twice → add it".
  [official — memory, features-overview]
- **Treat it like code**: review edits in PRs, prune regularly, test changes
  by observing behavior shifts. [official — best-practices]
- **Consistency review**: contradictory rules resolve arbitrarily — sweep the
  root file, nested files, and rules dirs together. [official — memory docs]
- **Revisit after model releases**: rules written around an older model's
  limitations actively harm a newer one; Anthropic deleted >80% of Claude
  Code's own system prompt for a new model. The radical form: periodically
  delete the file and watch what the model does before adding anything back.
  [official — large-codebases; opined — Cherny via YC Startup School notes,
  alex-jacobs.com "grievance archive"]
- **Symptom → diagnosis**: Claude ignoring a rule = file too long; Claude
  asking questions the file answers = phrasing ambiguous.
  [official — best-practices]
- Notably: **no sampled top-tier repo keeps dated log entries in the file** —
  evolution in the wild is either silent accretion (the anti-pattern) or
  offloading to skills/docs. A dated, pruned log (this plugin's model) is a
  deliberate deviation that trades file size for auditability — the pruning
  pressure is what makes it defensible. [observed — regex sweep across ~40
  files]

## 7. Anti-patterns

- **The over-specified file**: too long → Claude ignores half of it; prune
  ruthlessly, convert enforceable rules to hooks. [official — best-practices]
- **Append-only accretion**: changelog-voiced bullets piling up undated,
  never pruned (the 120 KB exemplar). [observed — OpenHands]
- **The grievance archive**: every entry written in peak frustration, never
  expiring, untestable in normal use. [opined — alex-jacobs.com]
- **Auto-generating and walking away**: auto-generated files measurably
  reduce task success (~3%) while raising cost (>20%). `/init` is a
  bootstrap, not an artifact — refine or hand-write.
  [measured — via philschmid.de; official /init docs disagree on the
  bootstrap value: genuine seam, both cited]
- **Pasting the harness's own reminders back** into the file, personality
  sections, duplicated system text. [observed — browser-use]

## 8. What NOT to optimize (the measured hierarchy)

The strongest evidence ranks the levers: **presence of a file ≫ content
relevance and brevity ≫ consistency ≫ everything structural.** Rule position,
section order, architecture, even self-contradiction produced no detectable
compliance difference in 16,050 observations; compliance decays with session
length and is far worse on edits than new code regardless of file craft.
[measured — arXiv 2605.10039]

For the structure review this means: prefer **deletions and relocations**
(sections 2 & 4) over rearrangements; never propose reordering for its own
sake; and treat "the file exists, is short, and doesn't contradict itself"
as the bar that matters.
