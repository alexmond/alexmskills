# Review & Roadmap

A snapshot of where **alexmskills** stands and what's next. Shipped history lives in
[`CHANGELOG.md`](CHANGELOG.md); this file is the forward view.

## Where it stands (review)

A public Claude Code plugin marketplace of **10 stable plugins** (each independently versioned) plus a
**beta channel**, dogfooding `evolving-claude-md` on itself, with Antora docs live at
[alexmond.org/alexmskills](https://www.alexmond.org/alexmskills/).

The centerpiece is **the Role System** — four plugins forming one system over a shared `.claude/roles/`
substrate of *evolving roles*:

| Plugin | Verb | Role |
|---|---|---|
| `roles` | — | shared substrate: evolving roles + solo `/roles:as` |
| `dev-crew` | **deliver** | composes a roster, runs a gated relay; escalation ladder, phase-gate hook |
| `brainstorm-panel` | **decide** | task-fit panel; skeptic-by-default, 1-round default |
| `research-sweep` | **discover** | parallel coverage roles → synthesize + adversarially verify |

The three orchestrators compose roles dynamically, learn per-repo, share a role vocabulary, and each runs
fully standalone (no-downgrade). All evolving state is written to the consuming repo's `.claude/`, never
the read-only plugin cache.

## Roadmap

### Open issues (tracked on GitHub)

| # | Item | Status |
|---|---|---|
| [#8](https://github.com/alexmond/alexmskills/issues/8) | Per-role model tiers across orchestrators | parked — the Fable slice was removed after 2026-06-12 (Fable 5 / Mythos 5 suspended by US government directive); revisit when access is restored |
| [#3](https://github.com/alexmond/alexmskills/issues/3) | Harvest universal learnings from repos back into marketplace seeds (graduation level 3 — `make harvest`) | not started |
| [#4](https://github.com/alexmond/alexmskills/issues/4) | CI guard for the read-only invariant | not started |

### Design threads (working drafts — open, not decided)

- **Ecosystem review + role-system design** — `docs/decisions/2026-06-12-ecosystem-review.md`.

### Harvest candidates (surveyed 2026-06-12 — not yet built)

From the other `~/IdeaProjects` repos, NEW assets worth generalizing (everything already harvested —
implement-issue, maven-quality, security-audit, review-agents, learn-on-failure, the orchestrators — is
excluded):

| Source | Candidate | What it gives | Reuse | Channel |
|---|---|---|---|---|
| (private repo) | **`add-engine-op`** | keep N parallel implementations in sync behind one interface + a contract test | HIGH | beta |
| (private repo) | **issue lifecycle** (`new-ticket` / `close-ticket`) | GitHub issue create/close with auto-labels + milestones — could extend `implement-issue` | MED-HIGH | beta |
| (private repo) | `implement` | module-placement + style-guided implementation (overlaps `implement-issue`; fold the best bits) | MED | — |
| unitrack | **PROFILE.md template** | documents a dev-crew roster + per-role tiers + pre-arm candidates — fold into `dev-crew` templates | MED | — |
| jsupervisor | Java 21 async-test rule | Awaitility async-assertion pattern — extend `maven-quality` | LOW | — |

Already-harvested duplicates seen and skipped: yj-schema-validator agents (`review-agents`), unitrack
`dc-*` agents (`dev-crew`).

### Future enhancements (from the design threads)

- Per-row `model` tier on `panel.md` / `research.md` for orchestrator-specific model overrides — currently
  every seat inherits the orchestrator's model. Ships as panel/research **1.2.0**.
