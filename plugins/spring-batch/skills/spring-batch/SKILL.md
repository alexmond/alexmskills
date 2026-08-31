---
name: spring-batch
description: Spring Batch 5/6 development — job repository wiring, restart versus a new JobInstance, flow and deciders, tasklet transaction boundaries, partitioning strategy, and testing. Use when writing or debugging a Spring Batch job, when a job "completes" having done nothing, when asking whether a job resumes after a restart, when choosing between a tasklet and a chunk step, when partitioning work across workers, or when a batch test passes and pins nothing. Grounded in runnable samples in spring-boot-playground.
---

## Spring Batch development

Every rule here was paid for. Where a claim has a measurement or a runnable
sample behind it, the source is named — prefer checking it over trusting this
file, and **correct the file when it is wrong** (see *Growing this skill*).

> **Ground new behaviour in the playground first.**
> `~/IdeaProjects/spring-boot-playground/spring-boot-batch-parent/` holds one
> module per mechanism, each asserting behaviour rather than describing it:
> `spring-boot-batch-restart`, `-flow`, `-tasklet`, `-partition`.
> When you are unsure what the framework does, **write the case there and run
> it** — that is what the modules are for. 17 tests, H2, no external services.

---

## 1. The default JobRepository stores nothing, and that is deliberate

**The single most expensive thing to not know.**

`spring-boot-starter-batch` plus a working `DataSource` yields
`ResourcelessJobRepository`. There is no `BatchJdbcAutoConfiguration` in Boot 4's
batch module — all eleven classes of `org.springframework.boot.batch.autoconfigure`
were checked.

**It is a design decision, not an omission.** `whatsnew.html`: it has been the
default since 5.2, "no longer requires an in-memory database (H2, HSQLDB) for
metadata storage", which "improves default performance and reduces memory
footprint". Knowing that changes how you argue about it: the framework is not
broken, it is optimised for the case where nobody restarts anything, and it does
not tell you which case you are in.

What that looks like: the job runs, every step executes, it reports `COMPLETED`,
and **nothing is written down**. Every execution comes back id `1`, no `BATCH_*`
table is created, and **restart does not exist** — not refused, absent. Nothing
warns you.

```
scan=d-1 execId=1 jobInstanceId=1
scan=d-2 execId=1 jobInstanceId=1      <- two different runs, same ids
tables: []
repository impl: ResourcelessJobRepository
```

**Ask for JDBC explicitly.** Batch 6 added `@EnableJdbcJobRepository` for exactly
this — store-specific configuration moved out of `@EnableBatchProcessing`:

```java
@EnableBatchProcessing(taskExecutorRef = "batchTaskExecutor")
@EnableJdbcJobRepository(dataSourceRef = "batchDataSource",
                         transactionManagerRef = "batchTransactionManager")
class MyJobConfiguration { }
```

Prefer that to hand-building a `JobRepositoryFactoryBean`. Hand-wiring still
works and is what you will find in pre-6 code, but it is now the older way, and
it brings the next problem with it: **declaring your own `jobRepository` bean
makes the context fail** with `BeanDefinitionOverrideException`, so it needs

```java
@SpringBootApplication(exclude = BatchAutoConfiguration.class)
```

`spring.main.allow-bean-definition-overriding` also starts, and resolves the
clash by letting whichever definition registered last win — the wrong fix for a
bean whose identity is the whole question.

`@Import(ScopeConfiguration.class)` registers the `step` and `job` scopes.
Without `@EnableBatchProcessing` nothing else does, and a `@StepScope` bean then
fails at startup with *"No Scope registered for scope name 'step'"*.

*Sample: `spring-boot-batch-restart`, `ResourcelessDefaultTest` pins the silent default.*

---

## 2. Restart means one thing only

- **New or changed content → a new `JobInstance`** (new identifying parameters).
- **An interrupted execution → the same `JobInstance` relaunched**, and it
  *resumes*: completed steps do not re-execute.

Measured, not assumed:

| case | result |
|---|---|
| same identifying parameters, already completed | `JobInstanceAlreadyCompleteException` |
| different parameters | new instance, everything runs again |
| interrupted instance, same parameters | **resumes — the completed step's body does not run again** |
| random per-launch token | failed instance orphaned, all work redone |

**`addString(k, v)` is identifying by default.** So
`addString("runToken", UUID.randomUUID())` makes every launch a new instance and
**makes resume unreachable**. If the trigger has an identity — a scan, an import,
a batch id — use it: `addLong("scanId", 42)`. Then a relaunch of the same scan
resumes, and a new scan is a new instance, enforced by the framework instead of
bypassed.

**Nothing marks a dead execution abandoned.** A JVM killed mid-run leaves
`BATCH_JOB_EXECUTION.status = STARTED` with `end_time` NULL, permanently. Spring
Batch cannot tell "still running" from "the process died". If you rely on
restart, mark stale executions abandoned at boot yourself.

**The only evidence of a resume is that the completed step's body did not run
again** — so a trace list per step is how you test it, not the status.

*Sample: `spring-boot-batch-restart`, `RestartSemanticsTest`.*

---

## 3. Flow: `ExitStatus` routes, `BatchStatus` records

`BatchStatus` is the recorded outcome. **`ExitStatus` is a string and the only
thing `on(...)` pattern-matches.** A step that *succeeded* can still route away
from the happy path by returning a custom `ExitStatus` from a
`StepExecutionListener` — the BatchStatus stays `COMPLETED` throughout.

```java
.start(inspect).on("DISCREPANCY").to(reconcile)
.from(inspect).on("*").to(report)
.end()
```

**A `JobExecutionDecider` is not a step and leaves no `StepExecution` behind.**
That is the point: it answers a question about the state of the world without
doing work. Model a gate as a decider, not as a step that completes having
processed nothing — otherwise "the gate was shut" and "the gate was open and
there was nothing to do" are the same row in the run history.

Restartability caveats bind only if you actually restart: `end()` sets
`COMPLETED` and the instance cannot be re-executed; `fail()` leaves it
restartable. If every launch is a new instance, neither applies.

*Sample: `spring-boot-batch-flow`, `FlowControlTest`.*

---

## 4. Tasklet vs chunk, and what `CONTINUABLE` really does

A chunk step is read/process/write with a commit every N items and the framework
owns the loop. A tasklet is one method; you own the loop, and it is re-invoked
while it returns `RepeatStatus.CONTINUABLE`.

**Each re-invocation runs in its own transaction.** That is how a long sweep
commits as it goes and survives being killed halfway. Verified by counting
`afterCommit` synchronizations: 5 invocations, 5 committed transactions,
corroborated by the step's own `commitCount`.

Two things measured to be false:

- **Batch 6 adds no final empty commit.** 7 items at chunk size 3 is **3**
  commits, not 4.
- **The current transaction's *name* cannot distinguish two transactions.** It is
  derived from the step and is identical on every invocation. Register an
  `afterCommit` synchronization and count instead.

*Sample: `spring-boot-batch-tasklet`, `TaskletShapesTest`.*

---

## 5. Partition by stride, not by contiguous range

The obvious partitioner gives worker k the range `[k*size, (k+1)*size)`. It is
correct and usually the wrong choice, because **ids are rarely in random order**
— they follow insertion order, which follows discovery order, which groups
similar items together. One block lands on the expensive material and the step
takes as long as its unluckiest worker.

A stride — worker k takes `id % n == k` — interleaves workers through whatever
ordering exists.

Measured, 60 items over 4 workers with cost clustered at one end:

| scheme | slowest worker | vs a perfect split |
|---|---:|---:|
| stride | 18,895 | **1.08×** |
| contiguous | 40,840 | **2.33×** |

Both cover the same population; only balance differs, and **the slowest worker is
the wall clock**. Stride is not perfect — the tail item still lands somewhere —
it is simply close.

*Sample: `spring-boot-batch-partition`, `PartitioningTest`.*

---

## 5a. A rerunnable reader: the process indicator

If you find yourself wanting a reader that does not save its position, the
framework already names the pattern — `readers-and-writers/process-indicator.html`:

> "many developers choose to make their database readers 'rerunnable' by using a
> process indicator. An extra column is added to the input data to indicate
> whether or not it has been processed."

A marker column, flipped when an item is written, plus a `WHERE PROCESSED_IND =
false`, plus:

```java
.saveState(false)   // the current row number is irrelevant on restart
```

The reader then "does not make any entries in the `ExecutionContext` for any
executions in which it participates."

**Why this matters more than it looks:** re-entrancy moves out of Spring Batch's
`ExecutionContext` and into your data model. The consequences follow from that
and are easy to hit by accident —

- restart is no longer the framework's job, so §2's `JobInstance` machinery stops
  being load-bearing;
- **the marker table is now the work queue**, which is what makes a second
  process a worker without a message broker (§9);
- but two readers will select the same rows unless the query claims them —
  `FOR UPDATE SKIP LOCKED`, or a lease column. The pattern gives you
  rerunnability, not concurrency.

If a project has built this by hand — a `WHERE NOT EXISTS (…done marker…)` reader
with an empty `update()` — it has implemented the process indicator. Say so, and
check `saveState` is actually false rather than merely unused.

---

## 6. A job that did nothing can report `DONE` at full population

`done` counts what the reader produced, not what the job attempted. A run in
which every item was skipped — file absent, precondition unmet — reports
`done = <the whole population>` and `COMPLETED`.

Model the outcome so the two cannot merge. An `Attempt`-style type with
`notAttempted` / `nothingToRecord` / `produced` keeps them apart, and the counter
must report **attempted** separately from **skipped**. A progress bar computed
from `done` will show a job that did nothing at 100%.

---

## 7. Configuration: bind objects, do not scatter `@Value`

`@Value` with a default cannot fail, so a misconfigured application starts and
produces a successful-looking run. A `@ConfigurationProperties` type can
**refuse to exist in a broken state** — `@Validated`, `@NotBlank`, or a
constructor that checks a directory exists.

For **library modules** (not `@SpringBootApplication`, not component-scanned),
put the annotation on the `@Bean` method:

```java
@Bean
@ConfigurationProperties(prefix = "photolens.work")
public WorkConcurrency workConcurrency() { return new WorkConcurrency(); }
```

Boot's `ConfigurationPropertiesBindingPostProcessor` binds an annotated `@Bean`
method without `@EnableConfigurationProperties`.

**Never default a required path or credential to the empty string.** A blank
archive root resolved every relative path against the working directory, found
nothing, and marked 31,568 assets "not attempted" while reporting success.

---

## 8. `spring-batch-test` — most projects declare it and never use it

| class | what it gives you |
|---|---|
| `JobLauncherTestUtils` | `launchJob()`, **`launchStep("name")`** — run one step, no job |
| `JobRepositoryTestUtils` | create and remove executions; clean between tests |
| `MetaDataInstanceFactory` | `JobExecution`/`StepExecution` fixtures **with no database** |
| `StepScopeTestUtils`, `StepScopeTestExecutionListener` | run inside a step scope so `@StepScope` beans resolve |
| `ExecutionContextTestUtils` | read values back out of execution contexts |
| `@SpringBatchTest` | wires the above into the test context |

Two traps: `JobLauncherTestUtils` assumes **exactly one `Job` bean** — call
`setJob(...)` explicitly in a multi-job context; and `MetaDataInstanceFactory` is
the answer when a test needs an execution but not a database, which is usually
the difference between a 20-second test and a 200-millisecond one.

---

## 9. Distribution: read this before reaching for a broker

Spring Batch Integration's remote chunking and remote partitioning need a
`MessageChannel`, in practice a broker. Before adopting one, check whether the
database is already the queue: if work is selected by a query and completion is
recorded in a table, a second application instance running the same job **is** a
worker, and needs `FOR UPDATE SKIP LOCKED` plus a lease rather than a channel.

**The reference documents no worker-death handling** — only a manager-side
`setReceiveTimeout`. Nothing on message loss, durability, or reassignment. It
assumes a worker fails gracefully; a killed JVM never replies. Verify this
yourself before depending on it; if it has changed, fix this section.

If a broker is genuinely needed, prefer **embedded Artemis**
(`spring.artemis.mode=embedded`) over ActiveMQ Classic, and **remote
partitioning** over remote chunking — partition metadata is small, items are not,
and the worker can usually read its own input.

---

## 10. API surface that moved (Batch 5 → 6 / Boot 4)

Checked against Batch 6.0.x. If you hit a class not where this says, **fix this
list**.

| symbol | package |
|---|---|
| `JobInstanceAlreadyCompleteException` | `org.springframework.batch.core.launch` (**not** `...core.repository`) |
| `JobParameters`, `JobParametersBuilder` | `org.springframework.batch.core.job.parameters` |
| `Job`, `JobExecution` | `org.springframework.batch.core.job` |
| `Step`, `StepExecution` | `org.springframework.batch.core.step` |
| `RepeatStatus` | `org.springframework.batch.infrastructure.repeat` |
| `ResourcelessTransactionManager` | `org.springframework.batch.infrastructure.support.transaction` |
| batch autoconfiguration | `org.springframework.boot.batch.autoconfigure` |
| `JdbcTransactionManager` (Spring 7) | `org.springframework.jdbc.support` (**not** `...jdbc.datasource`) |

`spring-boot-starter-batch` does **not** pull `spring-boot-starter-jdbc`.

**Consolidations in 6 worth knowing before you write a bean for one** —
from `whatsnew.html`:

- `JobOperator` **extends** `JobLauncher`; no separate `JobLauncher` bean.
- `JobRepository` **extends** `JobExplorer`; no separate `JobExplorer` bean.
- `JobRegistry` auto-registers jobs; `JobRegistrySmartInitializingSingleton` is gone.
- A `TransactionManager` is optional, defaulting to `ResourcelessTransactionManager`.
- `ChunkOrientedStep` (via `ChunkOrientedStepBuilder`) replaces
  `ChunkOrientedTasklet` / `TaskletStep`.
- Retry now uses **Spring Framework 7's** retry, not the Spring Retry library.
- `CommandLineJobOperator` replaces `CommandLineJobRunner`.
- Deprecated: `@EnableBatchProcessing(modular = true)`, JUnit 4 support in
  `spring-batch-test`, Jackson 2, the `batch:` XML namespace.

---

## Sources

- Reference: <https://docs.spring.io/spring-batch/reference/>
- Flow control: <https://docs.spring.io/spring-batch/reference/step/controlling-flow.html>
- Spring Batch Integration: <https://docs.spring.io/spring-batch/reference/spring-batch-integration.html>
- **`references/reference-map.md` — which reference page answers which question**,
  plus what each page settled when it was read in full. Start there rather than
  the docs index.
- Runnable samples: `~/IdeaProjects/spring-boot-playground/spring-boot-batch-parent/`

**Prefer the samples over this file.** Prose drifts; a test that runs does not.

---

## Growing this skill

This file is expected to be wrong eventually. When a session discovers a
behaviour, a version move, or a trap that is not here:

1. **Ground it in the playground first.** Add or extend a module under
   `spring-boot-batch-parent/` so the claim is a test, not a sentence. A rule
   with no runnable case behind it is the kind that rots quietly.
2. **Write the rule here with its evidence** — the measurement, the version it
   was checked against, or the sample that proves it. A claim with no provenance
   cannot be re-checked later, and this file is only useful while it can be.
3. **Correct rather than append.** If a section is now wrong, change it and say
   what changed. Two contradictory rules are worse than one stale one.
4. **Append a dated line to `references/learnings.md`** in this skill:

   ```
   - YYYY-MM-DD — what was believed → what is actually true, and how it was checked.
   ```

   Read that file when a rule here surprises you: it carries the corrections
   whose reasoning did not fit above.

**Measure before you write a number.** Several figures in this file replaced a
plausible guess that was wrong by more than an order of magnitude, and the guess
had already been quoted to someone by then.
