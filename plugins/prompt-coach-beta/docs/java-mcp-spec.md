# prompt-coach — Java MCP server spec (target architecture)

**Status:** living draft • **Last updated:** with `prompt-coach-beta 0.15.0`
**Update policy:** review + touch on every minor version bump. Anything that
would change the MCP surface, data model, or migration path gets logged here
first.

## Why

The current Python plugin is a `UserPromptSubmit` hook. It works for
Claude Code CLI, one user, local state only. Future needs the plugin can't
serve today:

- **Multi-user training data.** The rule catalog was tuned on a single
  maintainer's log. Real coverage requires observing many people's prompts,
  across many repos, across many editing styles.
- **claude.ai chat.** The chat product has no `UserPromptSubmit` hook.
  MCP servers *can* be connected to chat, so an MCP-shaped coach reaches
  a much larger surface.
- **Aggregate telemetry.** "Which rules fire, which never fire, which
  over-fire" needs cross-user aggregation — impossible from a per-user
  local log.
- **Persistent per-user state.** Mastery ledgers, config, refresher
  cooldowns should follow the user across devices.
- **Cross-language rule authoring.** The Python-only rule engine ties us
  to one runtime; a shared catalog format lets Python + Java + potentially
  a browser extension load the same rules.

## Target architecture (roughly 2027)

```
                    ┌────────────────────────────────────┐
                    │  Consumers                          │
                    │  ─────────                          │
                    │  Claude Code (CLI + desktop)        │
                    │    → uses MCP transport             │
                    │  claude.ai chat                     │
                    │    → MCP connector                  │
                    │  IDE plugins (VS Code, JetBrains)   │
                    │    → HTTP + SSE fallback            │
                    └────────────┬───────────────────────┘
                                 │ MCP (SSE / stdio)
                    ┌────────────▼───────────────────────┐
                    │  prompt-coach-service (Java)        │
                    │  ────────────────────────           │
                    │  Spring Boot 4.1 (matches the       │
                    │  maintainer's Java stack)           │
                    │  stack) + Reactor + MCP SDK         │
                    │                                     │
                    │  ┌─ MCP tools ────────────────────┐ │
                    │  │ analyze_prompt(prompt) → result│ │
                    │  │ get_stats() → per-user metrics │ │
                    │  │ configure(opts) → live config  │ │
                    │  │ report_bad_call(id, note) → ack│ │
                    │  │ list_active_rules() → catalog  │ │
                    │  └────────────────────────────────┘ │
                    │                                     │
                    │  ┌─ Rule engine ──────────────────┐ │
                    │  │ Loads canonical catalog        │ │
                    │  │ (rules.yaml @ HEAD)            │ │
                    │  │ Regex (RE2/J for safety)       │ │
                    │  │ Fuzzy: java-string-similarity  │ │
                    │  │ Phonetic: Commons Codec        │ │
                    │  │   Metaphone                    │ │
                    │  └────────────────────────────────┘ │
                    │                                     │
                    │  ┌─ Storage ──────────────────────┐ │
                    │  │ Per-user state → Postgres      │ │
                    │  │ Rate limiting → Redis          │ │
                    │  │ Telemetry queue → Kafka /      │ │
                    │  │   Redis Streams                │ │
                    │  └────────────────────────────────┘ │
                    └────────────┬───────────────────────┘
                                 │
                    ┌────────────▼───────────────────────┐
                    │  Aggregation pipeline (batch)       │
                    │  ────────────────────────           │
                    │  Nightly ETL over consented         │
                    │  telemetry → catalog quality        │
                    │  dashboards → PR-ready rule tuning  │
                    │  suggestions                        │
                    └────────────────────────────────────┘
```

## MCP surface (proposed)

The Java service exposes an MCP server. Consumer discovery per standard.

### Tools

**`analyze_prompt`**
- **Input:** `{ prompt: string, session_id?: string, repo_hint?: string }`
- **Output:**
  ```json
  {
    "analysis_id": "<opaque-uuid>",
    "fired_rules": ["vague-reference", "no-definition-of-done"],
    "chosen": "no-definition-of-done",
    "chosen_nudge_text": "You asked for an action but...",
    "positives_fired": [],
    "praise": null,
    "outcome": "nudged",
    "mode": "inline",
    "corrections": [["publish", "polish"]],
    "signature": {
      "word_count": 4, "starts_with_action": true, ...
    }
  }
  ```
- **Idempotent:** yes. Re-analysis of the same prompt returns the same
  fire pattern (subject to rule updates between calls).

**`get_stats`**
- **Input:** `{ scope?: "global" | "repo:<name>" | "since:<iso-date>" }`
- **Output:** parallel to `/prompt-coach-beta:stats` output today —
  prompt counts, nudge/praise counts, top-fired rules, mastered rules,
  active rules, config, top corrections.

**`configure`**
- **Input:** per-user config diff (`collaborator_gate`, `disabled_rules`,
  `praise_ratio`, etc.).
- **Output:** effective merged config after applying the diff.

**`report_bad_call`**
- **Input:** `{ analysis_id: string, class: "false-positive" |
  "false-negative" | "wrong-rule" | "bad-message" | "redundant",
  annotation: string }`
- **Output:** `{ ok: true, contribution_id: "<opaque>" }`.
- If the user opted into training-data contribution, the signature
  (never raw prompt) enters the anonymized aggregation queue.

**`list_active_rules`**
- **Input:** `{ tier?: 1..6 }`
- **Output:** per-user active + mastered rule set. Read-only view of the
  catalog with user's mastery status overlaid.

### Resources (optional, for chat surfacing)

- `catalog://rules` — full rule catalog with descriptions + sources.
- `catalog://positives` — parallel view for positive detectors.
- `docs://help` — the equivalent of `/prompt-coach-beta:help` output.

## Canonical rule catalog (shared source of truth)

Rules live in `catalog/rules.yaml` (proposed path, at repo root of the
service repo). Same file loaded by:

- **Python plugin** (transition period) — via a small loader that maps
  YAML → the current `Rule` dataclass.
- **Java service** — via Jackson binding + regex compilation at startup.

Example rule shape (draft):

```yaml
- id: no-definition-of-done
  tier: 1
  name: No definition of done
  check:
    kind: composite
    all:
      - fn: starts_with_action
      - not:
          any_marker_in_prompt: [until, verify, "so that", passes, green,
            expect, assert, "output should", "should return", coverage,
            "no error", acceptance]
  nudge: >
    You asked for an action but didn't say what 'done' looks like. Add
    one line: which tests pass, which behavior appears, or what output
    shape you expect.
  guidance: >
    User's prompt is an action verb with no acceptance criteria. Before
    acting, restate your interpretation of 'done' in one sentence, and
    invite a correction if it's wrong.
  sources:
    - anthropic-be-clear-and-direct
    - claude-code-best-practices
    - simon-willison
```

The `check` DSL is proposed lightweight — nothing that regex + a few
combinators can't express. Anything more complex than that keeps living
as native code (Python + Java parity), not YAML.

## Data model

### Per-user

```
users
  user_id (opaque UUID; not tied to email)
  auth_method (api_key | oauth_claude_ai | ...)
  consent_training (bool, default false)
  consent_at (timestamp)
  region (for data-residency)

state
  user_id
  scope (global | repo:<hash>)
  prompt_count
  updated_at
  # Serialized: {rules: {..}, normalization_stats: {..}, ...}

configs
  user_id
  scope
  keys → jsonb (collaborator_gate, praise_ratio, disabled_rules, ...)

analyses (short-retention rolling window)
  analysis_id
  user_id
  ts
  signature (jsonb, redacted)
  fired_rules
  chosen
  outcome
  ttl (default 30d, then hard-delete)
```

### Aggregated telemetry (opt-in only)

```
rule_fires (partitioned by day)
  date
  rule_id
  fire_count
  distinct_user_count
  (no per-user granularity)

false_positive_reports
  rule_id
  count_since_last_review
  top_annotations (first-5-words-only, capped, moderated)

missed_pattern_signatures
  signature_hash
  count
  top_annotations
```

## Privacy model

- **Opt-in only.** No telemetry leaves the user's device unless
  `consent_training = true`.
- **Content redaction is enforced server-side** — the MCP server refuses
  to accept a `report_bad_call` payload that contains anything beyond a
  structural signature + first-5-words + user annotation.
- **User-controlled deletion.** `/coach:forget-me` (or equivalent MCP
  tool) purges everything under that user id, including aggregate
  contributions attributable via `contribution_id`.
- **Aggregation-only surfaces.** Maintainer dashboards never show
  per-user data. Only aggregate counts. Per-rule top-annotations are
  first-5-words-only.
- **Regional data residency.** EU users' data stays in EU-region storage.

## Training data strategy

Two collection paths:

1. **Passive (opt-in, background)** — every analysis writes a signature
   row to `analyses`. Nightly ETL rolls into `rule_fires` aggregate.
2. **Active (explicit reports)** — user marks a bad call via
   `report_bad_call`. Contribution is a `false_positive_report` or
   `missed_pattern_signature` row.

Signal used:

- **Fire rate per rule** → rules that never fire (retire) or over-fire
  (tighten).
- **Emit rate on substantive prompts** → overall coverage.
- **False-positive rate per rule** → moving average; rules over a
  threshold get a review flag.
- **Missed-pattern signature clusters** → K-means on signature vectors;
  clusters → candidate new rules.
- **Praise-to-nudge ratio per user** → indicator that user's habits are
  actually improving vs stagnating.

Frequency: nightly aggregation, weekly maintainer review, monthly
catalog update PR.

## Migration path

1. **Parity freeze (v0.16.0, planned).** Extract the current Python
   rule catalog into `catalog/rules.yaml`. Python plugin loads from it.
   Zero-behavior-change refactor.
2. **Java service scaffolding.** Spring Boot 4.1 + MCP SDK. Loads same
   `rules.yaml`. Exposes MCP tools. No consumers yet.
3. **Parity tests.** For a corpus of 500+ prompts (the maintainer's log
   + curated test cases), verify Python and Java produce byte-identical
   analysis results.
4. **Alpha: dual-fire mode.** The maintainer + N consented users run
   BOTH the Python plugin AND connect to the Java MCP server. Compare
   outputs.
5. **Cutover.** Java service becomes canonical. Python plugin becomes a
   thin MCP client (calls the server, falls back to local rules if
   offline).
6. **General availability.** MCP server public at
   `prompt-coach.alexmond.org`, catalog contributions accepted via
   GitHub PR.

## Java implementation notes

**Stack:**
- Spring Boot 4.1 (matches the maintainer's other Java projects in the
  broader ecosystem).
- MCP protocol: Java SDK if one exists at build time, else custom
  SSE + JSON-RPC implementation.
- Regex: **RE2/J** (`com.google.re2j`) — linear-time guarantee, ReDoS-safe.
  Same syntax as `java.util.regex` for the subset we use.
- Fuzzy matching: **`tdebatty/java-string-similarity`** — Damerau-
  Levenshtein handles transpositions as 1 edit (dyslexic-typo scenarios
  benefit).
- Phonetic matching: **`apache commons codec`** — Metaphone /
  DoubleMetaphone. Better than pure Levenshtein for dyslexic misspellings
  like `nite → night`, `foto → photo` that don't reduce cleanly to edit
  distance.
- Persistence: PostgreSQL 16+. Self-hosted k3s deployment supported.
- Deployment: Docker → k3s.

**Non-goals for v1:**
- Live rule editing via UI (rules stay in YAML + git).
- ML-trained rules (regex is auditable; ML is not).
- Multi-tenant billing.

## Open questions

- **MCP Java SDK maturity.** As of the writing of this spec (2026-07)
  Anthropic ships Python and TypeScript MCP SDKs. Java community SDKs
  exist but maturity varies. Custom implementation is defensible; check
  before v0.16.
- **Rate limiting.** What's the per-user analysis rate? Naive answer:
  ~200/day/user (average Claude Code active user). Redis token bucket
  covers this.
- **Cost.** Self-hosted on homelab is free; if we go public and grow,
  costs are Postgres + Redis + a small compute unit. Ballpark $30/mo
  for a modest user base.
- **License.** MIT for the server, same as the current plugin. Rule
  catalog stays MIT so downstream forks can reuse.
- **Auth.** OAuth via claude.ai (best UX, requires their approval) or
  static API key (simple, works today).

## Related work in this repo

- `plugins/prompt-coach-beta/scripts/analyze-prompt.py` — current Python
  analyzer. Ground truth for behavior parity.
- `plugins/prompt-coach-beta/commands/report-issue.md` — bug-report
  workflow that already produces training-data-shaped payloads
  (structural signature + first-5-words + annotation).
- `plugins/prompt-coach-beta/docs/sources.md` — bibliography that will
  be preserved in the Java catalog.

## Update log

- 2026-07-03: initial draft. Motivated by the future MCP-server direction
  and the need to train on multi-user data.
