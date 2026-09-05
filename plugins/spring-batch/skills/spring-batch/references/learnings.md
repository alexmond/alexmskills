# Spring Batch — corrections log

Dated corrections whose reasoning did not fit in `SKILL.md`. Read this when a
rule in the skill surprises you: what is here is usually *why* the rule is
phrased the way it is.

Format:

```
- YYYY-MM-DD — what was believed → what is actually true, and how it was checked.
```

---

- 2026-08-30 — Believed `spring-boot-starter-batch` plus a `DataSource` gives a
  JDBC `JobRepository`. → It does not. Boot 4 ships no JDBC job-repository
  auto-configuration; you get `ResourcelessJobRepository`, every execution has id
  1, no `BATCH_*` table is created, and restart silently does not exist. Checked
  by listing all eleven classes of `org.springframework.boot.batch.autoconfigure`
  and by printing `repository.getClass()` in a running context.

- 2026-08-30 — Believed a job "continues" after a server restart. → Only if the
  *same* `JobInstance` is relaunched. A random per-launch parameter
  (`addString("runToken", UUID.randomUUID())`) makes every launch a new instance,
  so resume is unreachable. Proven in `RestartSemanticsTest`, then reproduced on
  a live 31,568-asset sweep: the killed run's record stayed `RUNNING` forever and
  a fresh run picked up the remainder from the *data model*, not from Batch.

- 2026-08-30 — Believed 7 items at chunk size 3 gives 4 commits (three chunks
  plus a final empty one). → It gives **3**. Asserted against
  `StepExecution.getCommitCount()`.

- 2026-08-30 — Believed the current transaction's *name* could show that
  `RepeatStatus.CONTINUABLE` commits between invocations. → It cannot: the name
  is derived from the step and is identical every time. Counting `afterCommit`
  synchronizations works — 5 invocations, 5 commits.

- 2026-08-30 — Believed stride partitioning lands within ~5% of a perfect split.
  → Measured 1.08× on clustered cost, against 2.33× for contiguous ranges. The
  bound in the test now comes from the measurement. Stride is not near-perfect;
  it is simply far better, and the *ratio between the two* is the argument.

- 2026-08-30 — Believed `JobInstanceAlreadyCompleteException` lives in
  `org.springframework.batch.core.repository`. → `...core.launch` in Batch 6.
  Compiler, not memory.

- 2026-08-30 — Believed declaring your own `jobRepository` bean simply overrides
  Boot's. → The context fails to start with `BeanDefinitionOverrideException`.
  Exclude `BatchAutoConfiguration`; do not reach for
  `spring.main.allow-bean-definition-overriding`, which resolves the clash by
  registration order.

- 2026-08-30 — Believed a job reporting `done = <population>` and `COMPLETED` had
  processed the population. → `done` counts items the reader produced, including
  ones the processor declined to attempt. Two live sweeps reported
  `done=31,568` having written zero rows, because a blank archive root made every
  file "absent". Report attempted and skipped separately.

- 2026-08-30 — Believed a per-file `exec` was an acceptable cost for metadata
  extraction. → 286 ms of every 298 ms was interpreter startup. But the
  replacement's *end-to-end* gain was 33.6×, not the 175× the component
  benchmark suggested: the job also does I/O and chunk commits. **Never quote a
  component rate as a system rate.**

- 2026-08-31 — Believed `ResourcelessJobRepository` being the default was an
  oversight in Boot 4's autoconfiguration. → It is a **deliberate Spring Batch
  decision since 5.2**: `whatsnew.html` says it removes the need for an in-memory
  database for metadata and "improves default performance and reduces memory
  footprint". The consequence (a job that reports COMPLETED and stores nothing)
  is unchanged; the framing was wrong, and the framing decides whether you argue
  with the framework or configure it.

- 2026-08-31 — Recommended hand-wiring a `JobRepositoryFactoryBean` to get a JDBC
  repository. → Batch 6 added **`@EnableJdbcJobRepository`** for exactly this,
  moving store-specific configuration out of `@EnableBatchProcessing`. The
  hand-wired form still works and is what pre-6 code looks like, but it is the
  older way and it drags in the `BeanDefinitionOverrideException` problem. Read
  the docs before recommending the workaround you happened to find first.

- 2026-08-31 — Wrote a section on "a reader that saves no state" as though it
  were a local invention. → It is a **documented, named pattern**: the *process
  indicator*, `readers-and-writers/process-indicator.html`, a marker column plus
  `saveState(false)`. A pattern with a name in the reference is a pattern other
  people's code and questions will use that name for. Search the docs for a name
  before describing a shape.

- 2026-09-05 — believed a `split` whose branches write to the same place is a defect needing a special merge step → actually that is the NORMAL case for partitioning, which is why `StepExecutionAggregator` exists; the defect is using a `split` where a `Partitioner` is meant. Checked against venice-vr, which has no `Partitioner`/aggregator/partition step at all and expresses two partition-shaped workloads as `split`. The diagnostic tell: with no aggregator available, the executor's concurrency limit becomes the only lever and ends up carrying write contention, host contention and caution as one number — so safety lives in a performance knob and is removed by tuning it. Added as SKILL.md §5b and grounded the same day in `spring-boot-batch-split` (`SharedTargetJobs` + `SharedTargetTest`): the SAME two-branch split leaves the shared target at 1 at width 2 and at 2 at width 1, both runs `COMPLETED` — so the case pins the knob, not the race. Remaining gap: a partition counterpart showing `StepExecutionAggregator` reconciling what the bare split corrupts.
