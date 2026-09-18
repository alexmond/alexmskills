# Learnings

Append when something in this skill proves wrong or incomplete, with the
measurement that showed it. Graduate into the body once a lesson has held across
more than one project, and prune the entry when you do.

Format: `- YYYY-MM-DD — <project> — what surprised you → what to do next time.`

- 2026-09-06 — venice-vr — seeded from one session: Flyway `common/{vendor}`
  split, checksum pinning after an edited shipped migration broke three
  deployments, the migrate-versus-validate authority split, the generation
  database, rehearsal across three deployments, `ddl-auto` defaulting to
  `create-drop` on embedded engines, `spring.flyway.*` being inert on Boot 4,
  and single-writer projections. **Unverified outside that project** — treat
  every rule as provisional until it holds somewhere else.

## Open questions this skill does not answer

- Zero-downtime column changes (expand/contract, backfill, `NOT NULL` in two
  steps) — deliberately absent; the source project deploys with brief downtime.
- `CREATE INDEX CONCURRENTLY` and lock-avoidance on large tables — not yet
  needed at the source project's row counts, so no measured guidance.
- Multi-tenant schemas (schema-per-tenant vs a tenant column) — the source
  project uses one database per deployment, which is a third answer and may not
  generalise.
- Logical replication as a migration route.
