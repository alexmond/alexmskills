# Single-writer projections

## The pattern

One process projects a curated source (files, an upstream system) into tables.
It is **one-way, single-writer, read-modify-write**, and it never deletes — it
sets a `retired_at` and leaves the row.

That property is load-bearing for everything downstream: it is what lets a read
path trust the tables, and what makes a performance rewrite safe (preserve
read-modify-write; do not "optimise" into a bulk upsert without checking who
depends on the semantics).

## Single-writer is a convention until you make it a control

Nothing stops a second writer. The next person will not know, and nothing will
tell them. Measured on a real projection, a rival row is:

- **overwritten** where the projection sets a projected column
- **hard-deleted** where the projection reconciles a child collection to the
  set difference
- **retired but kept** on the parent table

The damage differs per table, so a control that does not know which is which is
wrong about all of them.

## The fingerprint guard is narrower than it looks

A projection often skips work when the source has not changed. Read what the
fingerprint actually hashes: if it hashes the **source**, it is blind to a row
someone else wrote, and if it lives in an instance field it is **per-process** —
so a fresh process always projects and always destroys the rival row.

A rival row surviving one refresh is **the projection declining to run**, not
protection. Say so in the guard's own javadoc: a guard people believe is broader
than it is, is worse than no guard.

## The control

Four rules over main source, all derived:

1. a **write** method on a protected repository
2. an `EntityManager` persist/merge/remove of a protected entity
3. **raw DML** naming a protected table
4. a parameter typed as a repository **supertype** (the escape hatch)

Derive the protected set from the projection's own repository-typed fields, and
the protected tables from those entities' `@Table`. Derive the write-versus-read
split from the repository interface's own method names. Then a new repository on
the projection is absorbed with no edit.

Two things that make or break it:

- **Reads must stay legal.** A control forbidding all references gets disabled
  the first time a legitimate reader appears — and then protects nothing.
- **Scope to main source.** Tests construct projections and seed fixtures.

**Watch for a control that strips comments before matching**: string literals
are usually blanked by the same pass, and raw SQL lives in string literals. One
rule can stay silent while the other three fire.

## Where agent-authored state belongs

If something other than the projection needs to write, give it **its own
tables** — an override or correction layer, keyed to the same ids but distinct.
Then no table has two writers, and the read path composes them. This is the
answer to "an agent needs to edit the catalog": it does not edit the projection,
it writes overrides.
