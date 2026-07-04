# Changelog

All notable changes to the **alexmskills** marketplace and its plugins.

Plugins are versioned **independently** — the authoritative version is each plugin's `plugin.json`.
This log groups changes by date and tags each entry with the plugin and the version it shipped in.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/); the marketplace itself is
unreleased/rolling (no global version).

## 2026-07-03 (later 7)

### Added
- **prompt-coach-beta 0.19.0** — `/prompt-coach-beta:config` grew four
  new verbs to answer "what options exist?" and "how am I doing?"
  without needing to already know the answer.
  - **`options <key>`** — enumerates legal values with per-choice
    explanations. For enums (`nudge_style`, `voice_preset`,
    `voice_source`), lists each choice and what it does. For int/bool/
    list keys, shows current + default + example + description.
    Available in `--json` for the interactive flows.
  - **`quick` interactive flow** — orchestrated by the slash command
    file. Claude reads `options --json` for each of the categorical
    settings and presents `AskUserQuestion` pickers. Each answer routes
    to `:config set`.
  - **`full` interactive flow** — same pattern across every schema
    key. Enum keys → picker; int/bool → keep-current/type-new/reset-to-
    default. Longer flow; user can skip categories.
  - **`mastery`** — reads global `state.json` and renders a dashboard:
    mastered rules (with mastery date), in-progress rules (fires_total
    > 0, sorted by streak descending so closest-to-mastery surfaces
    first), dormant count by tier.
  - **`mastery-reset <rule-id>`** — zeros fires_total, clean_streak,
    status, mastered_at for one rule. Preserves prompt_count + other
    rules + non-schema keys. Dry-run preview first.
  - **`mastery-reset-all`** — same across every rule with accumulated
    state. Preserves prompt_count. Dry-run preview first.
  - **Schema addition**: enum entries in `CONFIG_SCHEMA` now carry an
    optional `choice_descriptions: dict[str, str]` — backward-compat
    (missing = no descriptions, still works). `nudge_style`,
    `voice_preset`, `voice_source` populated.
  - **Bug fix**: initial word-wrap for choice descriptions glued short
    tokens together (`+context`, `anti-disagreementguardrails`).
    Replaced with `textwrap.wrap()` for correctness.
  - **17 test categories verified**: schema coverage of new
    choice_descriptions, options for enum keys shows all choices +
    descriptions + current marker, options for int/bool shows
    default/example/description, options --json produces structured
    output with is_current/is_default flags, options for unknown key
    → exit 2, mastery on empty state (no state.json), mastery with
    populated state (mastered + in-progress + dormant counts + mastery
    dates), mastery --json, mastery-reset dry-run + actual with
    preservation checks, mastery-reset unknown-rule → exit 2, mastery-
    reset idempotent on clean rule, mastery-reset-all dry-run + actual
    with prompt_count preservation, backward-compat of existing verbs
    (show/describe/diff), analyze-prompt.py regression, E2E fire → mastery.

## 2026-07-03 (later 6)

### Added
- **prompt-coach-beta 0.18.0** — `/prompt-coach-beta:config` structured
  surface. The config catalog grew to 22 keys across 8 categories over
  v0.5→v0.17; say-it phrases still work for individual settings but the
  user had no scannable, categorized view. Fixed by adding a
  `CONFIG_SCHEMA` metadata dict alongside `DEFAULT_CONFIG` — every key
  carries `{category, type, choices, description, example, since}`.
  Future options are picked up automatically once they land in the
  schema, so the dashboard, describer, and validator never drift.
  - **9 verbs**: `show` (categorized dashboard), `show <category>`,
    `get`, `describe`, `set`, `reset`, `reset-all`, `diff`, `export`.
  - **Deep-merge writes** — preserves keys the schema doesn't know
    about (forward-compat with future versions).
  - **Schema-driven validation** on `set` — type coercion for
    `str/int/bool/list[str]/obj`, choice enforcement, clear error
    messages, exit 2 on bad input.
  - **8 categories**: output, voice, rule-activation, mastery, praise,
    typo-tolerance, anti-habituation, llm-fallback.
  - **Scoped**: `--scope global` (default) or `--scope repo` writes to
    the right config file. Resolution stays `default → global → repo`.
  - **`--dry-run`** on set/reset/reset-all previews without touching disk.
  - **`--json`** flag on show/get/describe/diff for scripting.
  - **Verified with 18 test categories**: schema coverage (every
    DEFAULT_CONFIG key has metadata, no orphans), show/describe/get,
    set with all 5 type coercions incl. 8 bool aliases, invalid-value
    rejection, scope isolation (repo doesn't leak to global), dry-run,
    forward-compat key preservation, diff, reset idempotency, export
    JSON validity, category filter + bad-category exit, reset-all
    dry-run doesn't delete, --json machine-readable output, and
    analyze-prompt.py still runs cleanly with the new schema imports.

## 2026-07-03 (later 5)

### Added
- **prompt-coach-beta 0.17.0** — voice presets + voice source + inline
  medium/short bug fix. Rolls three things into one release.
  - **Voice presets (`voice_preset`).** `Rule.nudge` now accepts
    `str | list[str] | dict[preset → list[str]]` — full backward-compat with
    v0.16's list form. Two presets ship: `colleague` (default; the current
    direct-ends-on-a-question voice) and `plain` (simple English, short
    sentences, no idioms, no jargon — for non-native speakers). L1 + L2 (10
    rules) ship both presets with 3 variants each = 60 phrasings. L3-L6 (18
    rules) fall back to `colleague` when `plain` is requested; those variants
    will be added as evidence surfaces which fire most.
  - **Voice source (`voice_source`).** Three options for who authors the
    nudge text at fire time:
      - `static` (default) — pre-written variants from the catalog; 0 tokens
      - `llm-compose` — Claude writes fresh, situated to *this* prompt with
        6 anti-disagreement guardrails baked into the additionalContext:
        header verbatim, never override the rule, ≤N words per disclosure
        level, must match preset voice, must end on a concrete ask, prompt
        shape provided so Claude can situate. Costs +200-800ms and ~150-400
        output tokens per fire.
      - `hybrid` — `static` on full fires (deterministic, teaching), 
        `llm-compose` on medium/short refreshers (livelier when repeating).
  - **Fixed v0.16 medium/short inline bug** — the medium and short inline
    context strings referenced "the variant text" but never interpolated
    the actual picked variant, so Claude improvised from `guidance` alone.
    Occasionally led to Claude *disagreeing with the rule* ("context
    resolves this one, proceeding") instead of delivering the coaching.
    Both paths now embed the picked variant text verbatim; the LLM-compose
    path is the intentional way to get situated composition, with
    guardrails that prevent the disagreement mode.
  - **Emit path logs `p=<preset>:src=<source>`** on every fire outcome,
    so `/prompt-coach-beta:stats` can mine which combination the user
    actually converges on.
  - **Say-it phrases**: *"set prompt-coach voice to plain"*,
    *"set prompt-coach source to llm-compose"*, *"set prompt-coach source
    to hybrid"*, etc.
  - **Verification**: 6 test categories pass — schema resolves all 3 nudge
    shapes; L3-L6 fall back cleanly when plain requested; `_pick_variant`
    honors config'd preset; `_resolve_voice_source` correct across all 7
    voice × level combos; E2E confirms static path embeds variant verbatim
    at every disclosure level; `llm-compose` emits all 6 guardrails in
    additionalContext.

## 2026-07-03 (later 4)

### Fixed
- **prompt-coach-beta 0.16.1** — inline-refresher bug + SKILL.md drift.
  - Fixed three code paths that rendered `rule.nudge` (now `list[str]`
    since v0.16.0) as a raw Python list literal instead of picking a
    variant. Affected: `_refresher_box`, `_inline_context_for_claude`,
    `_inline_context_for_claude_refresher`. All now use
    `rule.primary_nudge`; the picked-variant substitution in inline mode
    keeps working.
  - **SKILL.md drift cleanup.** Fixed accumulated inconsistencies:
    tier count 5 → 6, `no-answer-shape` moved from L2 table to L1 table
    (matches v0.12), `max_active_rules` default 5 → 6, `praise_ratio`
    default 3 → 10 (matches the v0.7 revert), added `inline` to the
    consolidated Configuration section, removed the duplicate Configuration
    block at the bottom, fixed the plugin id in "Verify it's on" from
    `prompt-coach@alexmskills-beta` to `prompt-coach-beta@alexmskills`
    (matches the v0.5-era channel retirement).
  - **help.md config surface updated** to include the v0.16 anti-habituation
    knobs (`saturation_threshold`, `silence_window`, `silence_duration`,
    `disclosure_medium_at`, `disclosure_short_at`) in both the CURRENT
    CONFIG and CONFIG OPTIONS REFERENCE sections.

## 2026-07-03 (later 3)

### Added
- **prompt-coach-beta 0.16.0** — anti-habituation (variant pool + novelty +
  progressive disclosure + silence-after-saturation). Motivated by real
  observation that seeing the exact same nudge text every fire trained the
  eye to skip it. Literature-backed (Hattie & Timperley 2007, Sasse & Rashid
  2013, ad-tech creative-wearout research) — variety + frequency capping +
  escalation is the combination that beats habituation.
  - **A. Variant pool** — `Rule.nudge` is now `list[str]` (backward-compatible
    via `Rule.nudges` property). L1 rules ship 3 hand-written variants each
    in a "colleague giving quick feedback" voice: direct, short, ends on a
    concrete question. Non-L1 rules keep single-variant for now, grow
    organically.
  - **B. Progressive disclosure** — box format depends on
    `fires_in_last_30_prompts`. First fire: full box (teaching). 2nd-3rd:
    medium (no sources, no progress line). 4th+: one-liner callout.
    Reflects "you've seen this, quick reminder."
  - **C. Novelty constraint** — picker tracks last 2 variant indices per
    rule; never picks a variant that's in the recent window if others
    are available.
  - **D. Silence after saturation** — 5+ fires within 30 prompts triggers
    a 30-prompt silence on that rule. Absence is a signal to the user
    that the coaching isn't landing.
  - **Voice rewrite for readability** — the initial variants read like
    a technical manual ("heavy verbs invite over-reach"; obscure
    idioms). Rewrote all 18 in a colleague voice ("You're asking for
    a big change but didn't say what to leave alone. What must NOT
    change?"). Much more direct, easier to act on.
  - E2E-verified: 7 consecutive fires of vague-reference on a fresh
    state produce {full, full, medium, medium, short, silenced, silenced}
    outcomes with all 3 variants used and no immediate repeats.
- Config: `saturation_threshold` (5), `silence_window` (30),
  `silence_duration` (30), `disclosure_medium_at` (2 fires),
  `disclosure_short_at` (4 fires).

## 2026-07-03 (later 2)

### Changed
- **prompt-coach-beta 0.15.0** — evidence-based rule fixes from a 75-entry
  post-reset log audit. Coach behavior on all 75 entries was reviewed;
  identified 30 substantive prompts that missed, tested each against v0.14
  rules, found 15 still-active gaps, and traced 7 to root causes with fixes:
  - **Hedge prefixes expanded** — added `i think`, `i feel`, `i want to`,
    `let me`, `now`, `actually`, `basically`, `so`. Evidence: prompts like
    *"now create new summary page..."* and *"i think X..."* had no action
    verb start visible to the analyzer.
  - **`ACTION_VERBS` +2**: `run`, `review`. Evidence: *"Run a brainstorm
    panel on..."* and *"review other prompts and find issues"* both fired
    zero rules.
  - **`no-role-for-critique` broadened** to match `review (other|these|
    previous|N|all|latest|recent|new)` in addition to the previous narrow
    set. `review` is now also an action verb, so no-DoD catches the same
    prompts as a fallback.
  - **`no-DoD` check-satisfaction tightened.** Removed standalone `"check "`
    from DoD markers — was falsely satisfied on prompts like *"commit and
    check infra for creds"* (investigative check ≠ verification). Added
    specific check-DoD patterns (`check that/it/the X works/passes/is
    green/builds`). Regression-tested against real DoD-check prompts
    (`"refactor auth and check it works"` still doesn't fire).
  - **`no-answer-shape` mid-sentence detection attempted, then reverted.**
    Relaxing the `^\s*` start-anchor to allow question forms anywhere
    over-fired on statements like *"refactor auth so it works no matter
    how do we scale"* and *"I already know how do i configure it"*. Kept
    strict anchor; two edge-case prompts (*"503 should be done can you
    check"*, *"i think boot support open telemetry can you check"*)
    accepted as misses.
- Coverage: 5 of 7 previously-still-missed prompts now fire correctly.
  Emit rate on substantive prompts (post-reset log): 40% → estimated ~55%
  once these v0.15 fixes are actually applied.

## 2026-07-03 (later)

### Added
- **prompt-coach-beta 0.14.0** — `/prompt-coach-beta:help` slash command.
  Compact dashboard-style help card with the live plugin version, current
  resolved config values (defaults → global override → per-repo override),
  the command list (stats / report-issue / help), all say-it phrases
  (mode/pause/disable/mark-bad-call), the full config option reference,
  and pointers to state files + docs. Read-only.

## 2026-07-03

### Added
- **prompt-coach-beta 0.13.0** — privacy-safe bug reporting workflow.
  - **Mark-phrase detection.** Say *"coach that was wrong"* / *"coach
    missed this"* / *"coach false positive"* / *"bad nudge"* on the turn
    right after a mistreated prompt. The analyzer flags the PRIOR
    substantive prompt's analysis (not the complaint itself) into
    `.claude/prompt-coach/candidates.jsonl`. Twelve trigger phrases,
    verified against 4 negatives ("this coach is helpful" / "please
    coach me" don't false-fire).
  - **`/prompt-coach-beta:report-issue` slash command.** Reads the
    candidates queue, computes a structural signature per case
    (word_count, starts_with_action, starts_with_hedge, has_file_ref,
    has_ticket_id, has_backticks, has_url, has_goal_clause,
    has_guardrail_clause, has_dod_marker, has_format_spec, is_question,
    is_conversational, corrections_applied), redacts prompt content to
    the **first 5 words**, and shows each case as a card. User adds a
    one-line annotation ("expected no-plan-mode-for-risky to fire") and
    optionally classifies (false-positive / false-negative / wrong-rule
    / bad-message / redundant). Full payload preview is shown; only on
    explicit "yes" does `gh issue create` post to `alexmond/alexmskills`
    with label `prompt-coach`.
  - **Privacy invariants** — verified by test: `first_5_words` is
    exactly 5 words, no full-prompt content leaks into any signature
    field, full prompts stay in local `log.md`.
- New `compute_signature(prompt, corrections)` public function on the
  analyzer for the slash-command to invoke.

## 2026-07-02 (latest 7)

### Changed
- **prompt-coach-beta 0.12.0** — log-mined 34 substantive missed prompts,
  found three fixable classes still slipping through:
  - **`no-answer-shape` elevated L2 → L1.** Info-seeking questions
    without a shape ("what are lsp servers", "Are there java libs...",
    "Do we have enough for release?") were firing nothing because
    L2 rules aren't active until L1 rules master. This is a fundamentals
    issue, not intermediate — belongs in the always-active L1 pool.
    Five real-log prompts get caught by the tier move.
  - **`no-answer-shape` q regex broadened** — added `do we/does it/can we/
    should we/did we/are there` question forms. Real English question
    shapes; the previous regex only caught `how/what/which/why/does exist`.
  - **`commit` added to `ACTION_VERBS`** — dev-workflow verb, evidence
    "commit and check infra for creds" fired nothing.
  - **`max_active_rules` default 5 → 6** to fit the new 6-rule L1 tier
    without displacing existing L1 rules. Config-overridable per repo.

## 2026-07-02 (latest 6)

### Added
- **prompt-coach-beta 0.11.0** — hedge stripping + release-family verbs.
  Evidence: a real-log prompt `"try to deploy"` fired ZERO rules — a
  genuinely risky no-DoD, no-guardrail ask that got silently ignored.
  - **Hedge prefix stripping** in `_starts_with_action` — strips
    `try to / try and / let's / going to / gonna / need to / want to /
    wanna / should / could / would / might / please / can you /
    could you / would you` before checking for an action verb. Real
    English almost never uses bare imperatives; the coach was missing
    everything that started with a hedge.
  - **`ACTION_VERBS` expanded** with the release family: `deploy`,
    `publish`, `release`, `ship`. Now the "try to deploy" class of
    prompt correctly fires `no-definition-of-done`.
  - **`missing-guardrails` heavy_action broadened** to include the
    release family + `reset`, `wipe`, `purge`. Deploys are near-always
    guardrail-worthy in practice.

## 2026-07-02 (latest 5)

### Added
- **prompt-coach-beta 0.10.0** — new **`nudge_style: "inline"`** mode. The
  nudge box is rendered as the opening block of Claude's response instead
  of going to stderr — so the coaching is visible *in your transcript*
  rather than in the dim hook-stderr area that some TUIs swallow.
  - Mechanism: `additionalContext` contains a rendering instruction plus
    the box, telling Claude to emit it verbatim at the start of the reply
    before addressing the task.
  - Costs ~50 extra output tokens per fire (small).
  - Also handles the v0.9 refresher tier — mastered rules render as a
    single-line callout instead of the full box.
  - Enable via config or by saying *"set prompt-coach to inline"*.
- Config: `nudge_style` now accepts `both | silent | log-only | inline`.
  Default remains `both`; users whose TUI doesn't visibly render hook
  stderr can flip to `inline` for guaranteed visibility.

## 2026-07-02 (latest 4)

### Added
- **prompt-coach-beta 0.9.0** — the "no permanent mastery" model. User's
  insight: even mastered rules should occasionally fire, and if a mastered
  rule matches a real prompt that's actually the *highest-signal event in
  the whole system* (evidence a habit is regressing).
  - **Refresher tier.** Mastered rules keep evaluating every prompt, but
    with a much longer cooldown (default 50 prompts vs 5 for practicing).
    When only a mastered rule matches, a softer box fires — one line,
    with the rule id and how long ago it graduated. No sources block, no
    progress bar. Emits as `🔄 prompt-coach — refresher on <rule>`.
  - **Priority preserved.** Nudge (practicing) > refresher (mastered) >
    praise. Kohn's don't-dilute principle still holds — refreshers count
    as "spoke this prompt" for the praise gate.
  - **Uncapped mastered evaluation.** Practicing rules still cap at
    `max_active_rules` (default 5). Mastered rules are bonus evaluators
    on top — they don't compete for a slot.
  - **Optional self-healing (`demote_on_regression`)** — off by default,
    opt-in. When enabled and a mastered rule fires threshold+ times within
    window prompts, demote back to practicing. Post-mastery fire counter
    is tracked either way (surfaced via `/stats`), so users can see drift
    even when auto-demotion is off.
  - **Backward-compat**: `mastered_cooldown_prompts: 0` in config reverts
    to pre-0.9 permanent-silence-on-mastery behavior.

## 2026-07-02 (latest 3)

### Added
- **prompt-coach-beta 0.8.0** — surfacing + praise coverage.
  - **`/prompt-coach-beta:stats` slash command** — read-only dashboard summarizing
    prompts analyzed, nudge/praise/skipped counts, emit rate, most-fired and
    mastered rules, top typo corrections, and current config. Answers "is this
    thing actually doing anything?" without opening `state.json` by hand.
  - **`cited-context` positive broadened** — now fires on ticket IDs
    (`RFJ-070`), file paths with extensions (`ENGINE-COMPARISON.adoc`,
    `src/api/auth.py`), backticked identifiers, URLs, and tech-name
    identifiers (`notify4j`, `spring-boot`). No longer requires a "the
    failing test" role phrase — the presence of ANY concrete grounding wins.
  - **New L1 positive `grounded-scope`** (mirrors `vague-reference` from
    the positive side) — praises substantive prompts (≥4 words) that
    include a concrete pointer, even without an explicit
    "the-X-role-phrase". Evidence: v0.7.0 log had 0 positive detectors
    firing on any of 34 real prompts, because the strict
    mirror-the-negative design missed real substantive prompts like "add
    both sections to ENGINE-COMPARISON.adoc". This closes that gap.
  - **`stated-goal` positive broadened** to match natural-voice reason
    clauses ("we are fully moved away", "the plan is …", "for the
    release") in addition to the textbook "so that / in order to" forms.
- Catalog: 28 rules, **22 positives** (+1 new L1). Slash command adds
  discoverability without expanding the rule surface.

## 2026-07-02 (latest 2)

### Added
- **prompt-coach-beta 0.7.0** — evidence-based improvements from log-mining a
  day of real prompts (34 across 6 sibling repos). Every change is keyed to a
  specific observed failure:
  - **False-positive typo corrections killed** (5/6 observed corrections were
    wrong: `changes → change`, `tickets → ticket`, `implemented → implement`,
    `publish → polish`, etc.). Two guards: (a) small curated `_PROTECTED_ENGLISH_WORDS`
    set for edge cases like `publish` ↔ `polish`; (b) English inflection guard —
    when the "correction" is literally the token minus a productive suffix
    (`-s`, `-es`, `-ed`, `-ing`, `-ly`, `-er`, `-est`, `-tion`, `-ment`, `-ness`,
    `-able`, `-ible`), skip it (real typos have insertions/substitutions elsewhere,
    not just a suffix strip). Preserves real dyslexic-style typos like
    `evrything → everything` (insertion) and `refacotr → refactor` (transposition).
  - **`ACTION_VERBS` broadened** with 15 real-session verbs the coach was
    missing — `move`, `open`, `close`, `branch`, `merge`, `file`, `format`,
    `install`, `configure`, `enable`, `disable`, `bump`, `pin`, `strip`,
    `gitignore` — plus multi-word phrases (`get rid of`, `clean up`, `set up`,
    `tear down`, `shut down`, `back up`, `hook up`, `wire up`). Catches
    prompts like "file tickets for RFJ-070" and "get rid of the github pages
    publish" that were silently ignored.
  - **`no-role-for-critique` broadened** to match `review results / findings
    / changes / the code / the output / design / plan` — plus `assess this`
    and `evaluate this`. Was previously narrow ("review this / my").
  - **New L2 rule `no-answer-shape`** — nudges when the prompt is `what are
    X` / `how much of Y` / `does Z exist` without a format spec. Would have
    caught 3+ real prompts from the day's log. Suggests "3-bullet summary
    each" / "yes/no + one line why" / "one-liner per".
  - **Task-notification short-circuit** — `<task-notification>` and
    `<system-reminder>` prompts (from task-triggered wakes in multi-agent
    workflows) now short-circuit through `is_conversational()` instead of
    being counted as user prompts. Was inflating mastery ladders across
    unitrack (many task-notifications) with meaningless "clean prompts."
  - **`praise_ratio` default reverted 3 → 10**. The v0.6.0 bump was
    compensation for the layer *appearing* not to fire (data-mining showed
    it fires plenty via `additionalContext` — you just don't see it every
    time). Kohn's don't-dilute-praise threshold is the right default;
    users can dial it down in config if they want visible reinforcement.
- Catalog: **28 rules across 6 tiers** (+1 new L2), 21 positives.

## 2026-07-02 (latest)

### Changed
- **prompt-coach-beta 0.6.0** — two behavior changes based on real-session feedback:
  - **Conversational short-circuit.** Many prompts are approvals (`sure`, `publish`,
    `go`, `ship it`), multi-choice picks (`1 and 2`, `a and b`, `option a`), or
    continuations (`continue`, `next`, `thanks`). The rules misfire on these and the
    typo normalizer over-corrects short conversational words (`publish` → `polish` at
    edit distance 2, then the coach nags about refinement). A new `is_conversational()`
    heuristic detects them BEFORE any rule matching / normalization and skips analysis
    entirely — prompt is logged with `outcome: skipped:conversational` for audit, but
    doesn't touch streaks, cooldowns, or praise counters. Same "approvals aren't the
    signal" principle as GitHub PR-approval comments not counting toward review-count
    metrics.
  - **`praise_ratio` default 10 → 3.** The 1-in-10 default was Kohn-inspired
    (don't-dilute-the-correction), but that's a steady-state value. During trial you
    need to see the encouragement layer *fire* to know it works at all. 3 is trial-
    friendly; bump to 8–10 in config once the layer has proved itself (a week of use).

## 2026-07-02 (later)

### Changed
- **Retired the beta channel entirely.** The `alexmskills-beta` marketplace
  (previously at `beta/.claude-plugin/marketplace.json`) is gone. In-progress
  plugins now live in the single stable marketplace with a `-beta` suffix in
  the name — the current examples are `prompt-coach-beta` (0.5.0) and
  `tune-repo-beta` (0.1.1). Same catalog, same install command, obvious at a
  glance that it's beta quality.
- **Why the pivot.** The two-channel setup kept hitting edge cases in the
  Claude Code CLI — bare-string plugin sources resolved from clone root vs
  marketplace-parent (fine for stable, broken for beta); `sparsePaths` not
  honored; dual `marketplace.json` at repo-root vs subdir confusing install
  vs `/reload-plugins`; `extraKnownMarketplaces` requiring per-user opt-in
  with a moving schema (`git-subdir` → `github` + path → `url`) — each
  workaround caught a class of user error but the surface area kept growing.
  One channel + a suffix convention removes every one of them.
- **Install path for beta plugins is now identical to stable.** No
  `extraKnownMarketplaces`, no `git-subdir` gymnastics — just:

  ```
  /plugin marketplace add alexmond/alexmskills
  /plugin install prompt-coach-beta@alexmskills
  ```

- **`make graduate PLUGIN=<name>-beta`** replaces `make new-beta` +
  `make promote`. Renames the directory (drops the `-beta` suffix),
  updates the plugin.json name, and rewrites the marketplace entry (drops
  the `beta` category + keyword). Follow with `make bump` to set a real
  release version.

### Removed
- `beta/` directory tree — the whole beta channel, README, and empty
  scaffold folders.
- `scripts/new-beta-plugin.sh` and `scripts/promote-plugin.sh` — replaced
  by `make graduate` for the one operation that survives.
- `extraKnownMarketplaces.alexmskills-beta` from `.claude/settings.json` —
  no separate marketplace to register.
- Beta-channel handling in `scripts/validate-marketplace.sh` — one channel,
  simpler validator.

## 2026-07-02

### Added
- **prompt-coach 0.5.0** (beta) — **typo tolerance**. A pre-pass normalizes each prompt against a
  curated set of ~90 trigger words drawn from the rule catalog, using a banded Levenshtein edit
  distance (custom, ~15 lines, zero deps). Dyslexic-friendly by design — the coach handles
  transpositions, dropped letters, and phonetic misspellings gracefully. Only substitutes on a
  **unique** closest match, and
  uses **adaptive tolerance** (distance-1 for tokens ≤ 6 chars, distance-2 for longer) so
  short-word collisions like `public ↔ rubric` don't produce false corrections. Examples that
  get fixed: `refacotr` → `refactor`, `evrything` → `everything`, `veryfy` → `verify`,
  `cleanre` → `cleaner`. Every correction is logged (raw + corrected in `log.md`; per-word
  frequency in `state.json`).
- **Self-report / health metrics.** New `normalization_stats` block in global state tracks
  `prompts_with_corrections`, `tokens_corrected_total`, and per-word `top_corrections`. Rising
  numbers signal that the regex rules aren't covering the user's actual prompts and are worth
  tuning. A parallel `llm_fallback_stats` block is stubbed for the v0.6 opt-in fallback (same
  signal, one level up).
- **Config knobs**: `typo_tolerance` (int, default `2`; `0` disables the whole normalization
  pass), `llm_fallback` (nested object, `enabled: false` default; v0.6 stub).

## 2026-07-01 (latest)

### Added
- **prompt-coach 0.4.0** (beta) — encouragement layer + L6 skill-awareness.
  - **Encouragement**: 21 *positive detectors* mirror the negative rules and praise the specific
    positive behavior (not the absence of a negative), e.g. `stated-metric`, `stated-guardrails`,
    `provided-example`, `asked-plan-first`. Praise is *sparing* — default 1-in-10 clean prompts
    (variable-ratio, per Skinner) + always on rule mastery + always on first-after-fire
    (immediate correction after being nudged). Never emitted on a prompt that also got a nudge
    (Kohn 1993). 2–3 rotated phrasings per positive with a light touch of warmth/humor. Config:
    `praise_ratio` (default 10), `praise_on_mastery` (default true),
    `praise_on_first_after_fire` (default true), `disable_praise` (default false). Grounded in
    Mueller & Dweck 1998 (process praise > trait praise), Fogg 2019 (celebration → habit),
    Brophy 1981 (functional analysis of teacher praise), Deci & Ryan 2000 (autonomy-supportive
    framing), Kohn 1993 (don't dilute the correction).
  - **L6 skill-awareness** (new tier, 3 rules): `no-skill-lookup` ("how do I X" without checking
    for an existing skill), `pattern-worth-abstracting` ("again / same as before" — rule of
    three), `no-skill-composition` (multi-step ceremony not named as a skill candidate). Plus
    2 positives: `invoked-skill` (used a slash-command / named a skill), `abstracted-to-skill`
    ("let's make a skill for this"). Grounded in Fowler *Refactoring* (rule of three), Kent
    Beck's YAGNI, Anthropic Claude Code Skills docs, McIlroy's Unix philosophy (composition),
    Norman *Design of Everyday Things* (discoverability > memorability).
- **Total catalog**: **27 rules across 6 tiers** + **21 positive detectors**. On the smoke-test
  suite (49 positive+negative fixtures across all new detectors), all pass.
- (v0.3 was folded into 0.4 — never externally released; single bump.)

## 2026-07-01 (later)

### Added
- **prompt-coach 0.2.0** (beta) — advanced-concept coverage. 13 new rules across three
  areas the v0.1 catalog missed:
  - **L3 classical prompting** (4 new): `no-few-shot` ("like X" without an example),
    `no-chain-of-thought` (why/debug/trace ask without "think first"), `no-rubric`
    (judgment ask without axes), `no-uncertainty-budget` (investigative ask without
    an "if unsure, say so" clause). Adds Wei et al. 2022 (CoT), Brown et al. 2020
    (few-shot), and Anthropic multishot/CoT docs to sources.
  - **L4 goals & loops** (new tier, 3 rules): `implicit-goal` (action without a
    stated outcome/why), `unbounded-iteration` ("keep improving" without a stopping
    condition), `no-rubric-for-refine` (refinement without naming which axis).
  - **L5 Claude-Code tool-native** (new tier, 6 rules): `no-plan-mode-for-risky`,
    `no-task-list-for-multi-step`, `no-agents-for-parallel-lookup`, `no-role-for-critique`,
    `no-panel-for-contested-design`, `no-workflow-for-fanout`. These nudge you toward
    your own tool chest (Plan mode, TaskCreate, parallel Explore/Agent, /roles:as,
    brainstorm-panel, Workflow) when the prompt shape calls for it.
- Total catalog: **24 rules** across 5 tiers. `max_active_rules=5` still caps how many
  can nag at once — L1 masters first, then L2 rules slot in, and so on. On the
  smoke-test suite (26 positive+negative fixtures for the new rules), all 26 pass.

## 2026-07-01

### Added
- **prompt-coach 0.1.0** (beta) — new plugin in the `alexmskills-beta` channel. A
  `UserPromptSubmit` hook analyzes every prompt sent to Claude Code against a tiered ruleset of
  prompting best practices (L1 fundamentals: vague-reference, no-definition-of-done,
  unbounded-scope, improve-without-metric, missing-guardrails; L2 intermediate: compound-tasks,
  no-verify-loop, missing-context-fetch, no-format-spec; L3 advanced: no-adversarial-check,
  retry-without-diagnosis). One nudge per prompt, per-rule cooldowns, tier-progressive graduation:
  a rule masters after N clean prompts in a row (default 15), which activates the next dormant
  rule. Rules cite ≥2 sources drawn from Anthropic prompt engineering docs, Claude Code best
  practices, OpenAI's prompt engineering guide, Simon Willison's notes, and *The Prompt Report*
  (Schulhoff et al., 2024) — see [`docs/sources.md`](beta/plugins/prompt-coach/docs/sources.md).
- **Nudge style is configurable**: `both` (stderr box + `additionalContext` for Claude; default),
  `silent` (Claude only), `log-only` (no output, log the fire). Config resolves local
  (`.claude/prompt-coach/config.json`) → global (`~/.claude/prompt-coach/config.json`) → default.
- **State: global mastery + per-repo overrides**. Global ledger at
  `~/.claude/prompt-coach/state.json` tracks fires and mastery across every repo; local state at
  `.claude/prompt-coach/state.json` records per-repo fires and lets a repo *reactivate* a globally
  mastered rule (e.g. the rules that stayed on for a Java repo but should be re-taught in a docs
  repo).
- **Say-it affordances** for common toggles — *"coach pause 10"*, *"coach off vague-reference"*,
  *"set prompt-coach to silent"* — Claude edits the right config/state file. No slash commands
  yet; the SKILL.md documents the phrasing.
- **Non-blocking, deterministic, cheap.** Pure regex heuristics, no LLM call; runs in ~10 ms; if
  it errors, the hook prints the error to stderr and exits 0 so your prompt never gets blocked.

## 2026-06-29 (later 2)

### Fixed
- **marketplace.json source schema** (closes #28) — every plugin in both channels migrated from
  the silently-broken `{source: "github", repo, path}` object form to the canonical relative-path
  string form (`"./plugins/<name>"` for stable, `"./plugins/tune-repo"` for beta). The `github`
  source type **only supports `repo`, `ref`, and `sha`** — it silently ignores `path`, cloning
  the full repo and putting `installPath` at the repo root, where Claude Code then fails to find
  any plugin's `.claude-plugin/plugin.json` or `skills/`. Every external user who tried
  `/plugin install <name>@alexmskills` since the marketplace launched got a silent no-op
  install. Found by an external bug report (initially misdiagnosed as a CLI bug) traced back to
  upstream issue [anthropics/claude-code#43811](https://github.com/anthropics/claude-code/issues/43811)
  (closed by the original reporter as "user error, wrong source type"). Sampled 5 well-known
  public marketplaces (anthropics/claude-code, wshobson/agents, daymade/claude-code-skills,
  obra/superpowers, affaan-m/everything-claude-code) — every one uses the relative-path string
  form. We were the outlier.

### Changed
- **`scripts/validate-marketplace.sh`** — hard-fails on any plugin source that uses
  `{source: "github", path: <anything>}` to prevent the regression. Validator now teaches the
  correct alternative in the error message.

## 2026-06-29 (later)

### Changed
- **brainstorm-panel 1.2.1** (closes #25) — make the unanimity guard *auditable*. Audit across
  47 panel runs in 5 sibling repos found that 30% of runs were round-1 unanimous but **0 logs
  ever recorded the steelman guard firing** — the 1.1.0 anti-groupthink remedy was invisible
  in practice. Two changes:
  - Log entry template now requires a `Steelman:` field whenever R1 was unanimous, with one of
    four outcomes (`ran, opposing view was X — retained | adopted | panel reversed` /
    `waived because <reason>` / `n/a — pushback present in R1`). Silent unanimity is now
    indistinguishable from groupthink and must be called out.
  - SKILL.md prose reframed: unanimity is a **risk signal**, not a positive outcome to
    celebrate. New log wording: *"5/6 aligned — note: low dissent; opposing view considered
    was Y"* over the older *"strong cross-role convergence"*.
  - Anti-anchoring (seats see only the question in R1, no prior synthesis — `affaan-m/ECC
    council` mechanism) is **deferred**, contingent on a revalidation pass after 10+ new runs
    with the auditable guard. Goal is the cheapest fix that turns invisible-guard into evidence.

## 2026-06-29

### Changed
- **brainstorm-panel 1.2.0** / **dev-crew 1.2.0** — graduation now routes to the right layer of
  the role substrate, not flat into CLAUDE.md. Three-layer split is now explicit in both SKILL.md
  files:
  - **Per-role wisdom** (how the role *behaves in this orchestrator*) → the role's row in
    `.claude/roles/{panel,crew}.md`.
  - **Cross-context wisdom** (true in panels + crew + sweep + solo) → graduation *candidate*
    for the shared core role file `.claude/roles/<role>.md` `## Learnings (core)` (user-gated;
    only when the `roles` plugin is installed).
  - **Repo facts about seating** (always seat X here; default lineup per category) → the small,
    terse `## Panel roles` / `## Dev crew` block in `CLAUDE.md` — *not* the place for per-role
    wisdom or generalized lessons.

  Why: a sibling-repo audit found that flat graduation to CLAUDE.md was leaving per-role wisdom
  invisible to the orchestrators that don't seat the role first, defeating the shared-role-
  substrate premise. Discovered by `unitrack`'s Restraint Skeptic (5×+) and QA/SDET (4×+) never
  lifting, and `builder`'s UI-five roster (6×+) never lifting — all because the only documented
  destination was the wrong layer.

### Added
- **roles 1.1.0** — new sub-skill `/roles:evolve` that closes the "graduation gets a learning
  *in*, but nothing keeps the role file useful *after*" gap. Audits each role file across four
  dimensions: *consolidation* (≥3 Learnings entries on one topic → propose merge),
  *staleness* (Learnings citing files/symbols no longer in the tree, excluding `.claude/roles/`
  itself to avoid self-reference false positives → propose strike), *body-drift* (≥3 core
  learnings contradict the Charter/Body → propose refresh), and *solo→core graduation*
  (≥3 solo entries on one topic + role used by ≥2 consumer registries → propose lift). Engine
  is `scripts/evolve-roles.py` — pure regex + `git grep`, no LLM, wall-clock budget-capped
  (~4s). All proposals user-gated; never silently rewrites a role file. Complements the
  existing reactive SessionStart `roles-init-audit.py` hook with an actionable deep pass.

## 2026-06-27 (later)

### Added
- **screenshot-tour 1.0.0** — new plugin: build a presentation-ready screenshot deck of the
  current product for demos, slide decks, and stakeholder walkthroughs. Three phases:
  *discover* (read README + entry points + `--help`/routes + recent CHANGELOG → propose 5–12
  numbered aspects in `presentation/plan.md`, user-gated), *capture* (one recipe per aspect
  under `presentation/recipes/`, using the right tool per surface — the project's existing
  browser driver for web (defaults: Selenium-Java for JVM repos, Playwright for Node/Python),
  Charmbracelet VHS for CLI/TUI, Charmbracelet Freeze for code and output stills, manual
  fallback for OS dialogs / mobile / hardware), *assemble* (captioned narrative-ordered
  `presentation/tour.md`, optional ImageMagick contact sheet). Self-learning via
  `.claude/screenshot-tour/log.md` → graduates stable invariants into a `## Screenshot tour`
  block in the repo's `CLAUDE.md`. Slide-deck export, README integration, and docs-site
  embedding are opt-in follow-ups, not the default.

## 2026-06-27

### Added
- **evolving-claude-md 1.1.1** — adds **merge** as the fourth downward pressure in SKILL.md,
  closing a loop gap discovered while dogfooding: when CLAUDE.md hits the audit's "compaction
  RECOMMENDED" level but every entry is <14 days old, graduation (needs 14-day stability) and
  quarterly archive (needs an old-enough cutoff) are both blocked. Merge collapses same-session
  same-area clusters (phased rollouts like `e2a` / `e2b` / `e3` / `e4`; multi-aspect bursts
  within ~48h) into one consolidated entry without claiming the pattern has stabilized — keeps
  the load-bearing whys, splits per-aspect detail out to `docs/decisions/{date}-{topic}.md` if
  still wanted, and is reversible (split a sub-decision back out via strike-through follow-up
  if it evolves independently). Discovered while compacting `jvmlens`'s 37-entry / 25 KB log.

## 2026-06-26

### Added
- **evolving-claude-md 1.1.0** — three audit upgrades after a sibling-repo survey found that
  none of the live CLAUDE.md files were triggering compaction even though most were past the
  Claude Code whole-file size pressure. Three changes:
  - **Whole-file size check** in `audit-claude-md.py` (warn 25 KB, recommend 40 KB) — the
    actual context-pressure dimension. Catches bloat that lives outside `### Decisions &
    Learnings` (Conventions / Architecture / Gotchas / Changelog) which the entry/line
    counters never saw.
  - **Self-report when D&L is missing** — a CLAUDE.md without the section no longer exits
    silently; the audit reports total file size + dated-bullet count and recommends wiring
    `evolving-claude-md`. This is what was hiding the bloat in repos like `builder`.
  - **Staleness trigger** (closes alexmskills#16) — extracts backticked artifact-looking
    tokens (paths, `ClassName.method`, `--cli-flags`, `<xml-tags>`, known-extension
    filenames) from each entry, runs `git grep -qF` against the tree, flags entries citing
    ≥2 missing tokens. Wall-clock-budget-capped (~2.5s) so the hook stays under its
    timeout. Gives the loop a *delete* lever, not just a *compress* lever.

## 2026-06-21

### Added
- **research-sweep 1.1.3** — closes the cross-run learning gap (the only orchestrator without
  a per-run log). Four changes:
  - **Per-run log** at `.claude/research-sweep/log.md` (seeded from a shipped schema), with
    fields for run-id, roster, partition, per-role volume + thin-diagnosis, verifier findings
    (sample, fabrications, duplicates, gaps, verdict), dedup hotspots, source-trust, steering,
    outcome, and graduations.
  - **Thin-agent diagnosis** — classifies thin results as *slice-thin* (corpus sparse → merge /
    lower target) vs *agent-thin* (web denied / weak prompt / wrong angle → re-run / re-role),
    mirroring crew's capability-vs-ownership ladder. Logged as `thin:` events.
  - **Demote / retire rule** — two thin runs (no fix) → probationary; three → retired. Three
    user-cut events at the roster gate also retire the role.
  - **Graduation block** — patterns holding across ≥3 sweeps in a repo graduate into a
    `## Research sweep` block in CLAUDE.md (default roster, authoritative sources, untrusted
    sources, ID-disambiguation rules, skip-angles); graduated entries are pruned from the log.

## 2026-06-14

### Added
- **tune-repo 0.1.1** *(beta)* — new plugin: a one-shot audit-and-tune skill that calibrates a
  repo's `CLAUDE.md`, verify loop, static guardrails, and permission allowlist to its house
  style (using the closest well-tuned sibling repo as the template). Three phases — discover →
  audit → propose-then-apply — with an `audit` keyword for report-only mode. The calibration
  counterpart to `evolving-claude-md`'s ongoing maintenance loop. Ships on the **beta**
  channel.

### Changed
- **beta marketplace.json** — switched to the explicit `{source: github, repo, path}` form
  (parity with stable's 2026-06-12 fix); older Claude Code CLIs (≤v2.1.153) reject the
  bare-string `pluginRoot`-relative shorthand.

## 2026-06-13

### Removed
- **brainstorm-panel 1.1.2** / **research-sweep 1.1.2** / **dev-crew 1.1.1** — all references to the
  **Fable** model tier (the opt-in Fable suggestion at the roster checkpoint; the architect/lead
  Fable-eligible flags + escalation policy in dev-crew; the conductor-never-on-Fable rule; the design
  doc `docs/decisions/2026-06-12-fable-model-selection.md`). Reason: Anthropic suspended Claude Fable 5
  and Mythos 5 on 2026-06-12 in response to a US government export-control directive citing a potential
  jailbreak; the timeline for restoration is unclear. Issue #8 is parked. Re-add when Fable returns.

## 2026-06-12 (later)

### Added
- **brainstorm-panel 1.1.1** / **research-sweep 1.1.1** — the roster checkpoint now emits an opt-in
  **Fable suggestion** grounded in the orchestrator's bottleneck: the panel (generation-bound) recommends
  one deep "visionary" generator seat on Fable (rest stay Opus for diversity); the sweep
  (verification-bound) recommends the skeptic-verifier (+ optional synthesizer) on Fable, scouts stay
  Opus. Never default. Design rationale: `docs/decisions/2026-06-12-fable-model-selection.md` (issue #8).
- README **"The Role System"** section — the four role-system plugins (`roles` + the three orchestrators)
  presented as a dedicated block, not just rows in the catalog.

## 2026-06-12

### Added
- **roles 1.0.0** — new plugin: a per-repo repository of *evolving roles* (`.claude/roles/`) usable
  four ways — solo (`/roles:as <role>` + per-persona skills), as dev-crew roles, brainstorm-panel
  seats, and research-sweep coverage roles. Ships seed personas (`architect`, `builder`, `debugger`,
  `optimizer`, `reviewer`, `refactorer`, `skeptic`), a SessionStart index + graduation-audit hook,
  and the shared-core convention. Absorbs the former `senior-prompts` beta plugin.
- **research-sweep 1.1.0** — joins the role system as the **"discover"** orchestrator: coverage-roles
  registry `.claude/roles/research.md`, dynamic angle composition from the information space, archetype
  coverage roles (`entity-scout`, `timeline-scout`, `source-scout`, `container-scout`) + probationary
  minting, a shared `skeptic` verifier + a synthesizer, and per-repo learning.
- **dev-crew 1.1.0** — escalation protocol (`BLOCKED` handoff + diagnosis-driven ladder), a
  machine-enforced phase-gate hook, handoff discipline, qa verify-against-reality, a `ui-reviewer`
  candidate role, and an axis-driven roster compose path.
- **brainstorm-panel 1.1.0** — a panel roles registry (`.claude/roles/panel.md`), skeptic seated by
  default, a unanimity→steelman guard, a 1-round default, pre-proposed practitioner/buildability seats,
  acceptance re-review, evidence capture, prefs-outrank-veto, and adaptive stopping.
- In-depth **Role System** architecture documentation; a naming convention for plugins and roles
  (documented in `CLAUDE.md`); a **Provenance & attribution** section in the README.

### Changed
- **Renamed** `parallel-research-sweep` → **`research-sweep`** (drop the redundant qualifier; join the
  crew/panel/sweep family).
- **Renamed** role personas to crew-aligned nouns: `build-app`→`builder`, `system-design`→`architect`,
  `debug-root-cause`→`debugger`, `optimize-perf`→`optimizer`, `understand-refactor`→`reviewer`,
  `clean-arch`→`refactorer`; coverage roles `by-*`→`*-scout`.
- **dev-crew** description reframed: the crew composes a *task-fit roster* to deliver a target —
  `architect → dev → qa → deployer` is one example lineup, not the definition.
- Read-only correctness: evolving plugins write state to the consuming repo's `.claude/` (or user
  memory), never into the read-only plugin cache; shipped `roles.md`/`log.md` are read-only seeds.

### Promoted
- **roles** promoted from the beta channel straight to the stable catalog (1.0.0).

## 2026-06-11

### Added
- Initial marketplace scaffold: `.claude-plugin/marketplace.json`, the `plugins/` layout, a jq-based
  validator, `Makefile`, CI (`validate.yml`), MIT `LICENSE`, and the Antora docs component (`docs/`).
- Stable plugins, all **1.0.0**: `evolving-claude-md`, `dev-crew`, `brainstorm-panel`,
  `learn-on-failure`, `implement-issue`, `maven-quality`, `security-audit`, `review-agents`,
  `parallel-research-sweep`.
- **Beta channel** (`alexmskills-beta` under `beta/`) with `make new-beta` / `make promote` tooling,
  and the `senior-prompts` beta plugin (later absorbed into `roles`).
- Trigger samples and copy-paste install blocks across the README and docs.
- The repo **dogfoods** `evolving-claude-md` on its own `CLAUDE.md`.
