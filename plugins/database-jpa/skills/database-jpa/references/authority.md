# Migration authority: who may apply, who may only validate

## The rule

**Exactly one artifact may apply a migration. Everything else validates and refuses to start on a mismatch — in either direction.**

Validate-only means: the process compares the migrations it carries against the database's history and *fails at its own startup* if they disagree. Not "ignores extra", not "applies what is missing". Both directions matter — a process **behind** the database writes silently-wrong rows, and a process **ahead** of it is about to.

## Why an app must not migrate itself

The tempting arrangement is that the application applies its own migrations at boot. It is convenient exactly once, and wrong for a reason that has nothing to do with correctness of the DDL:

**A pod restart is not a decision.** Kubernetes reschedules on node pressure, eviction, a liveness blip. If boot means migrate, then arbitrary DDL applies at a moment nobody chose, with no operator watching, no backup taken, and afterwards no way to tell whether the schema moved because someone meant it to.

The severity scales with the size of the pending change. A restart that applies one nullable column is survivable. One that applies thirty-one tables is not something to discover from a monitoring alert.

## The shape that works

```
  vantagetn-web-app      runtime dep on the schema module   VALIDATE
  admin/ops server       runtime dep on the schema module   VALIDATE
  schema CLI             runtime dep on the schema module   MIGRATE  ← the only one
  everything else        test scope only                    tests own their database
```

Two properties make this auditable rather than conventional:

- **Split the verbs into separate methods.** `SchemaCheck.validate(...)` and `SchemaCheck.migrate(...)`, never one method with a boolean. Then "which artifacts may apply a migration" is answerable by grepping for call sites, and a test can pin that list.
- **Never expose `clean`.** Not behind a flag, not behind a profile. A method that does not exist cannot be called by accident.

### Pin the consumer list

A test that reads both facts *out of the tree*:

- which modules take a runtime dependency on the schema module (parse the poms, skip `<scope>test</scope>`)
- which files call the migrate method (scan `src/main/java`)

Both derived, both compared against a short named list. A new carrier or a new caller then fails the build naming itself. Assert non-vacuity on both — a scan that finds zero poms passes forever.

## The deploy sequence changes

Once the app validates rather than migrates:

```
1. run the schema CLI against the deployment's database
2. THEN roll the pods
```

Getting the order wrong fails **loudly**: the pod exits at startup naming the two versions, rather than serving over a schema it does not understand. That is the trade — a rollout that stops, instead of an app that half-works.

The natural end state is an **initContainer** running the CLI in front of the pod, so a failed migration stops the rollout itself rather than being a step someone remembers. Design the CLI for that from the start: config entirely from env/args, no TTY, no prompts, idempotent, one line per outcome on stdout, and distinct exit codes with *both* success cases (applied / nothing-to-do) at 0.

## Where a migrate grant legitimately lives

Exactly one place: **beside a disposable database the caller just created.** A local-development script that starts a throwaway container may export the grant in the same breath.

The principle is that **the grant follows the disposable database, not a profile name.** A profile is a word someone types, and the URL beside it is whatever the shell happens to hold. Granting on a profile means the grant travels to whatever database that shell is pointed at.

Corollary: an absence needs a control. Removing the grant from a deployment profile is one line, and *re-adding* it is one line. Nothing fails until the day a migration goes wrong. Assert the absence — scan every shipped `application*.yaml`, derived from the tree so a profile added later is covered, and assert the base profile still defaults the flag to false. Without that second half the first is meaningless: an absent key that inherits a permissive default achieves nothing while every assertion still passes.

## Framework trap: the config key that does nothing

On Spring Boot 4, Flyway's auto-configuration ships in a **separate module**. If that module is not a dependency, every `spring.flyway.*` key in the project is **inert** — present, plausible, and doing nothing. A key that looks like the lever and is not is worse than no key, because it stops people looking for the real one.

Check before relying on any framework property that gates schema behaviour: does anything actually read it? The reliable lever is a property your own code reads, feeding your own `validate`/`migrate` call.

## Cross-check

Any process that can reach a deployment database should refuse to run against one whose schema it does not match — derived on both sides (migration filenames versus the applied history), never a hand-maintained "expected version" constant. A constant goes stale exactly when it matters.
