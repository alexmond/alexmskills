# Engine portability: decided when the file is written

## The rule

**A fresh database replays version 1 before the newest version exists.** So
portability is decided at the moment each migration is written, and a construct
only one engine supports forks that file per engine *permanently*. No later
migration can retire the fork.

This is the asymmetry to internalise: everything else about a migration can be
corrected by a follow-up. Portability cannot.

## Layout: one folder per engine, nothing in the parent

```
db/migration/common/        portable DDL — the default
db/migration/postgresql/    the production engine's fork
db/migration/h2/            the test engine's fork
```

**Nothing directly in `db/migration/`.** A Flyway location is scanned
**recursively**, so a file in the parent is found by every engine — resolving
twice ("more than one migration with version N") or applying the wrong engine's
DDL. Both failures are silent until they are not.

Configure the locations as `common` + `{vendor}`, resolved from the connection.

## What forks, and what to reach for instead

| construct | portable? | note |
|---|---|---|
| `CREATE INDEX … WHERE` (partial) | **no** | forks forever; weigh whether the index is worth it |
| `jsonb` | **no** | see below — the failure is silent |
| identity/serial syntax | varies | prefer the SQL-standard form |
| `TEXT` | yes | the safe default for string columns |
| `TIMESTAMPTZ` | yes | prefer over `TIMESTAMP` for anything time-ordered |
| plain single-column indexes | yes | keep in `common/` |

### The jsonb trap

A `jsonb` column that some driver writes as a string produces:

```
ERROR: column "x" is of type jsonb but expression is of type character varying
```

…logged, **the run carries on, and records nothing.** The job looks like it
worked. Use `TEXT` and hold JSON in it; retyping a shipped `jsonb` column later
means a deployment behind that point silently records nothing until it catches
up.

## Portability is not the same as parity

Testing on an embedded engine and deploying on a real one is fine, but the test
engine's schema must come from **the same migrations**, not from a generated
one. See `jpa.md` on `ddl-auto`.

Also test the **production major version**, not just whatever the test container
happens to pin. A replay against `postgres:16` proves little about 18 if you use
anything version-sensitive; run the real version once by hand under
`ON_ERROR_STOP=1` and count what you got.

## Index the referencing side of foreign keys

Postgres does **not** index the child side of an FK. Every delete or key-update
on the parent then scans the child to enforce the constraint.

Add an index for each FK column that is not already the leading column of the
primary key or a unique constraint. Two cautions:

- **An inline `col TYPE PRIMARY KEY REFERENCES …` is already indexed.** A check
  that only recognises table-level `PRIMARY KEY (...)` reports these as missing.
  Measured once: 11 findings, 7 of them false for exactly this reason.
- **Do not extend this into a general index pass.** Other indexes need query
  evidence; an index added on a guess is a write cost paid forever. FK columns
  are different because the constraint itself is the reader, and it exists the
  moment the table does.
