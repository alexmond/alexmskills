# When a shipped migration is wrong

## The rule

**A migration a deployment has applied can never be edited.** Not renamed, not
reformatted, not "only a comment". Flyway records a checksum; changing one byte
makes every deployment holding it fail validation at its next boot.

The fix for a wrong shipped migration is **a new migration**.

## The failure that teaches this

A repo-wide rename sweep touched a comment inside a shipped migration — one
character, `application.yaml` → `application.yml`. The checksum changed. The
pin that existed to catch exactly this was **refreshed to match**, because that
made the build green.

All three live deployments then failed at boot. The pin had done its job and
been overruled; refreshing a pin alongside the edit it guards *records* the
drift instead of preventing it.

**So: a pin refresh in the same commit as the edit it guards is the smell.**
Reverting the edit is the fix.

## Pin every shipped checksum

A test holding `version → checksum` for every shipped migration, asserted
against what Flyway computes. Then an edit reddens the build instead of a
deployment's next boot.

Two properties matter:
- **Adding a pin for a NEW migration is correct.** Changing an existing pin's
  value is the sin. Say that in the test's own comment, because the two look
  identical in a diff.
- The failure message must name the deployments at risk, not just the mismatch.

## The window: before it ships, it is free

A migration no deployment has applied is fully editable — *including its pin* —
provided every test and generation database is **dropped and replayed** rather
than migrated forward.

This is worth exploiting deliberately. Iterating on DDL is cheap while the
window is open and impossible afterwards, so front-load the changes you are
unsure about. Fold pending schema work into the unshipped migration instead of
queueing a follow-up.

**State which side of the line you are on** in any commit touching a migration,
so nobody later cites an in-window edit as precedent for editing a shipped one.
The window closes at the first deploy that carries it — not at merge, not at
tag.

## The generation database

The pattern that makes the window usable, and the safe route for a large change
even after it closes:

1. Create `<db>_v<N>` beside the live database — a **generation counter for
   which copy is live**, deliberately not the schema version.
2. Restore from a dump of live. Verify table-by-table *before* migrating.
3. Apply the new migrations there. Wrong? Drop it and redo — free.
4. Load and verify.
5. Flip one connection string. Keep the old database until the new one is trusted.

Rollback is the same one string. Any tooling that guards "which deployment is
this database" must accept the suffix, or every call needs an override typed by
hand — and a guard worked around on every invocation is a guard that gets
switched off.
