# JPA against a schema you do not generate

## `ddl-auto` stays `none`, and the default is not `none` where it matters

Flyway owns the schema. Hibernate must never generate it.

**Spring Boot defaults `ddl-auto` to `none` against a real database but
`create-drop` against an EMBEDDED one.** So a test suite on in-memory H2 will
silently replace the *shipped* schema with one generated from the entities, and
every test then passes against a schema no deployment has. State `none`
explicitly in every module's config, including the hand-built factories tests
use.

## Prove the mappings match the shipped DDL

Entities and migrations drift the moment they are edited by different people.
The control: migrate a database from the real migrations, then compare each
`@Entity`'s table and columns against it.

Two arms, and the second is the one usually missing:

1. **Names.** Every mapped table exists; every mapped column exists.
2. **Keys.** Every entity's id-set is exactly its table's primary key.

Arm 1 alone passes for an `@IdClass` naming the wrong subset — which compiles,
starts, and fails at runtime as a `findById` that misses a row that is there.
Composite keys arrive in batches when a schema lands, so this is worth having
before that happens.

**Name the not-yet-mapped entities rather than excluding the package.** A named
list that shrinks to empty is a visible metric; a package exclusion makes the
test pass by covering nothing.

## Repositories

- **A bare `JpaRepository<Row, Id>` is enough** until a query is genuinely
  needed. Speculative finders are untested surface.
- **Pin the repository's `ID` type argument against the entity's key type.**
  `JpaRepository<FooRow, String>` over an `@IdClass` entity compiles and starts.
  Nothing else checks it.
- **Every entity reachable through exactly one repository** — assert it, so a
  new entity cannot be silently unreachable.

## Watch the framework's reach

A `@Configuration` class inside a widely-scanned package is active in **every**
context that scans that package, including test-jars on consuming modules'
classpaths. A `@ConditionalOnProperty` on the class that imports it buys
nothing.

If a config class is meant to be opt-in, **leave the stereotype off** —
`@Import` alone makes it a configuration class, and the annotation adds only
reachability by the scanner. The failure looks like an unrelated test failing to
load a context.

## Batch/job frameworks

If the persistence layer also hosts a job framework, check whether its
auto-configuration launches jobs at startup. Some launch *every* job bean when
no specific job is named — so an unrelated CLI invocation silently runs a batch
job too. Exclude the launcher auto-configuration and launch explicitly.
