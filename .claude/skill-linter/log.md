# skill-linter log

Dated record of misses (a defect the linter should have caught) and false positives
(a finding that was not a real problem), plus what changed as a result.

Both directions matter. A miss costs one bad skill; a false positive costs the
linter's credibility, which costs every future skill.

Format: `- YYYY-MM-DD — **kind** — evidence → change.`

## 2026-08-08 — first run, alexmskills

Ran against 24 skills across 14 plugins. No errors; 18 warnings, 11 info. The two
entries below are false positives found by the first run and by the harness, both
fixed in the shipped checker rather than as learned rules, because both were
defects in the rule itself rather than gaps in coverage.

- 2026-08-08 — **false-positive** — `broken-reference` fired three times on
  `screenshot-tour` for `01-hero.gif`, `02-install.png`, `NN-outcome.png`. All
  three sit inside a fenced Markdown template that the skill tells you to
  *generate*; `NN-` is a placeholder. Skills also deliberately show bad patterns
  in fences. → Added `strip_fences()`; every content rule now reads the body with
  fenced blocks blanked out (line numbers preserved). Harness pins both
  directions: fenced examples never fire, the same defects in prose still do.

- 2026-08-08 — **false-positive** — `description-first-person` fired on the
  linter's own reference description, matching `my` inside the quoted user phrase
  `"lint my skills"`. Descriptions are supposed to quote what users type, and
  users say "my" and "you" — so the rule was punishing exactly the phrase-listing
  that `description-no-phrases` asks for. → Added `strip_quoted()`; person checks
  run on the author's voice only, with quoted spans removed.

- 2026-08-08 — **coverage note** — `description-no-trigger` fired on 9 skills, 8
  of them the `roles/*` personas, which all end "Invoke explicitly." That is a
  deliberate design choice (they are dispatched by name), not a defect. Left as a
  warning rather than adding a veto: the cost is real — every description occupies
  context in every session whether or not it can ever fire — so it deserves to
  stay visible until the trade is confirmed. Revisit if the answer is "yes, on
  purpose", and record it as a per-repo learned rule with `enabled: false`.

## 2026-08-13 — pre-release sweep

- 2026-08-13 — **miss** — `claude plugin tag --dry-run plugins/skill-linter` rejected
  the linter's *own* SKILL.md: `YAML frontmatter failed to parse`. The description
  ended `…Learns: a defect it failed to catch becomes a new rule.` — a bare `word: `
  on a continuation line, which real YAML reads as a nested mapping and rejects
  outright. **Claude Code loads such a skill with empty metadata, so it can never
  trigger** — the plugin had been broken since it shipped, and `lint-skills` called it
  clean every time. → Root cause was the hand-rolled parser: it never supported
  multi-line *plain* scalars at all (only `>` and `|`), so it silently accepted what
  YAML rejects. Rewrote `parse_frontmatter` around three explicit scalar modes and
  made a `word:` continuation inside a plain scalar a hard `frontmatter-invalid`.
  Verified all 25 skills now agree with `yaml.safe_load` on valid/invalid, and pinned
  that agreement as a harness check so the parser can't drift lenient again.

  The lesson generalises past this bug: **a lenient parser standing in for a strict
  one launders broken input as clean, which is worse than not checking at all.** Any
  hand-rolled substitute for a real parser needs a conformance test against the real
  one, not just its own unit tests.

## 2026-08-18 — deep review of the marketplace

- 2026-08-18 — **miss** — `review-agents` shipped three agents using
  `allowed-tools:` — the slash-command field, silently ignored in agent
  frontmatter — so agents documented as "read-only" ran with the full tool set
  (Write, Edit, `git push`) since 1.0.0. Found by a manual deep review, not by
  the linter, because the linter did not look at `agents/*.md` at all.
  → 0.2.0: agents are first-class lint targets. `check_agent()` validates
  frontmatter, name↔filename, trigger-bearing description, and two new rules:
  `agent-wrong-tools-field` (ERROR — the exact miss) and `agent-unknown-tool`
  (WARN — a misspelled tool grants nothing, silently). The trigger regex also
  learned the word "agent" ("Use this agent when…"), which its skill-only
  wording rejected — that FP would have burned trust on the first agent run.

- 2026-08-18 — **coverage note** — `script-unreferenced` only inspects a
  `scripts/` subdirectory. `evolving-claude-md` ships its .py files FLAT beside
  SKILL.md, so its unmentioned `test-harness.py` evades the rule — the exact
  claim (run-vs-read intent per bundled script) applies, the layout doesn't
  match. Not widened yet: flat-layout matching needs calibration against the
  69-skill corpus first (risk: flagging fixture/data .py files). Widen if a
  second flat-layout case appears, or mention harness files in their SKILL.md.

- 2026-08-18 — **false-positive** — skill-creator's `agents/{grader,comparator,
  analyzer}.md` are that skill's subagent INSTRUCTION documents (deliberately
  frontmatter-free), not Claude Code agent definitions; linting them as agents
  produced three false ERRORs. → agents/ now counts only at a plugin root
  (sibling `.claude-plugin/`) or under `.claude/`. Harness-pinned.
- 2026-08-18 — **coverage note** — `discover()` does not follow symlinks, so a
  `~/.claude/skills/` tree of live-skill symlinks lints only its regular dirs
  (8 of 26 here). Worked around by resolving targets before the run; following
  symlinks in rglob needs a loop guard before it ships.

- 2026-08-18 — **false-positive** — `workflow-step-gap` fired on adapt-workflow's
  `Step 2 / 3 / 6` sections, which are deep-dives into selected steps of a full
  numbered flow list above — not a broken sequence. → the rule now fires only
  when the heading sequence starts at Step 1 (a sequence that claims to be
  complete). A genuinely deleted step keeps its Step 1. Harness-pinned.
