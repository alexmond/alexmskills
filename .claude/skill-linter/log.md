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
