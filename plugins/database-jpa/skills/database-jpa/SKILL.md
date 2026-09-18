---
name: database-jpa
description: >
  Flyway + JPA schema lifecycle on Spring Boot 4 — who may apply a migration versus who may only validate one, what to do when a shipped migration is wrong, rehearsing a change against every deployment before it ships, engine-portable DDL, and keeping a projection single-writer. Use when writing or reviewing a Flyway migration, when a deployment fails at boot on a checksum, when choosing a column type that must work on more than one engine, when deciding whether an app may migrate itself, when mapping entities to a shipped schema, or when a migration passed on one database and you are about to apply it to others.
---

## Database schema and JPA lifecycle

Every rule here was paid for, and most were paid for twice — once when
something broke, and once when the control that should have caught it turned
out to be measuring the wrong thing. Where a claim has a measurement behind it,
the measurement is named. **Prefer checking it over trusting this file, and
correct the file when it is wrong** (see *Growing this skill*).

The recurring shape, worth stating before any specific rule: **a schema failure
is rarely loud.** It is a run that reports success having written nothing, a
guard that refuses in a way indistinguishable from passing, a coverage figure
measured over the wrong population, or an app quietly applying DDL nobody
decided to apply. Design every control here to fail *loudly* and to prove it
ran, because the default failure mode of this whole area is silence.

## References

| Area | Resource | When to use |
|---|---|---|
| Migration authority | `references/authority.md` | Deciding who may `migrate` and who may only `validate`; deploy sequencing; initContainers |
| Editing a shipped migration | `references/shipped-migrations.md` | A migration is wrong and a deployment already has it; checksum pins; the generation-database escape |
| Rehearsal before shipping | `references/rehearsal.md` | More than one deployment, or any deployment whose data you have not imported yet |
| Engine portability | `references/portability.md` | Multi-vendor migration folders, partial indexes, type choices that fork forever |
| JPA against a shipped schema | `references/jpa.md` | Entities, composite keys, repositories, `ddl-auto`, proving mappings match the DDL |
| Single-writer projections | `references/projection.md` | One process owns a table; making that a control rather than a convention |
| Controls that hold | `references/controls.md` | Writing a check that cannot pass vacuously; RED-first evidence |

## The rules that bind before you read anything else

1. **Only one artifact may apply a migration.** Everything else validates and
   refuses. If an app can migrate itself, then a pod restart — an event nobody
   decided on — can apply arbitrary DDL with no operator watching and no backup
   taken. See `references/authority.md`.

2. **A shipped migration can never be edited.** Not renamed, not reformatted,
   not "just a comment". The fix for a wrong shipped migration is a *new*
   migration. Refreshing a checksum pin to match an edit records the drift
   instead of preventing it. See `references/shipped-migrations.md`.

3. **Until it ships, it is free.** A migration no deployment has applied can be
   edited freely, *including its pin*, provided every test database is rebuilt
   from scratch rather than migrated forward. The window closes at the first
   deploy. State which side of that line you are on before touching a migration
   file.

4. **A green run on one deployment is not evidence about the others.** Schema
   replays are portable; *data* is not. Foreign keys added in a new migration
   are enforced against each deployment's own accumulated rows. See
   `references/rehearsal.md`.

5. **Portability is decided the moment a file is written**, because a fresh
   database replays version 1 before the newest version exists. A construct only
   one engine supports forks that migration per engine permanently. See
   `references/portability.md`.

6. **A control must prove it ran.** "It passed" and "it ran" are different
   facts, and a scan that resolves the wrong directory satisfies its rule
   forever. See `references/controls.md`.

## Growing this skill

Append to `references/learnings.md` when something here proves wrong or
incomplete, with the measurement that showed it. Graduate a learning into the
body above once it has held across more than one project; prune it from the log
when you do. A rule with no evidence behind it is a preference — mark it as one
or remove it.
