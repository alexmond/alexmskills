# Rehearsing a schema change against every deployment

## The rule

**A green migration on one deployment is not evidence about the others.**
Rehearse every one before the change ships, because fixing it afterwards needs
a new migration and the mistake is already in production.

## Why one deployment is not enough

The DDL is the portable part and will usually replay anywhere. What differs per
deployment is **data**, and a migration that adds referential integrity is
enforced against each deployment's own accumulated rows.

Deployments diverge in ways that are invisible until you try:

- **Different starting versions.** One may be several migrations behind, so its
  replay covers a path no other deployment has ever executed.
- **Different domain shape.** A deployment of a different kind (photographs
  rather than paintings; an empty entity set) exercises different columns.
- **Different accumulated debris.** Each has its own orphan rows — sidecar
  records naming parents that were deleted. Before the FK existed they were
  silent; afterwards they abort the import.

The last one is the killer, because the orphans are *per deployment* and nobody
has counted them.

## Two rehearsals, and only the second is likely to fail

1. **dump → replay.** Restore a generation from a dump of live, apply the
   migrations. Proves the SCHEMA migrates for that deployment's history.
2. **project → import.** Load the real data into the migrated generation.
   Proves the DATA fits the new constraints.

**A green (1) with no (2) is the shape of evidence that gets mistaken for
proof.** Only the second exercises foreign keys. Run the import over the *whole*
population, not a sample — the point is that every row passes the constraint.

## Gate the live apply, not the build

A build-time control that fails until every deployment is rehearsed will redden
the trunk for every unrelated change and be switched off within days. **Wrong
place.**

Bind it at the irreversible act: the migrator **refuses to apply a pending
migration to a live database unless a rehearsal for that deployment and that
version is on record.** Give it a distinct exit code — "right database, too
early" is not the same failure as "wrong database".

Design notes that turned out to matter:

- **Ask per pending version**, never "highest rehearsed", so an old rehearsal
  cannot vouch for a new migration.
- **Pin a digest of the migration's own bytes** in the record. Then an edit to a
  still-editable migration makes the rehearsal stop counting, and the message
  says *"rehearsed, then changed"* rather than *"not rehearsed"* — a materially
  different instruction.
- **Never gate a generation database.** Running a generation is how a record
  gets written; gating it deadlocks the gate.
- **A malformed record line must throw, not be skipped.** A skipped line is a
  rehearsal the gate silently stops asking for.
- Ship the record **inside the artifact** so an initContainer can read it.
- **No override flag.** The way past the gate is to run the rehearsal.

## Consequence to plan for

Every edit to an unshipped migration **invalidates every rehearsal of it**. That
is the mechanism working, but it is real work: re-run one command per
deployment before the first live apply. Sequence rehearsals *after* the
migration has stopped changing, or budget for repeating them.
