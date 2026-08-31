# Spring Batch reference — which page answers which question

Base: <https://docs.spring.io/spring-batch/reference/> (6.0.5 at time of writing).
Append the path below. **Check the version banner on the page** — this map was
built against 6.0.5 and the tree moves between majors.

## When you need to…

| question | page |
|---|---|
| what changed in 6, what was removed | `whatsnew.html` |
| the vocabulary — Job, JobInstance, JobExecution, StepExecution | `domain.html` |
| wire the JobRepository, DataSource, transaction manager | `job/configuring-infrastructure.html` |
| **choose a JobRepository implementation** | `job/configuring-repository.html` |
| launch a job, pass parameters, restart one | `job/running.html` |
| `JobOperator` — start, stop, restart, abandon | `job/configuring-operator.html` |
| read execution metadata, query past runs | `job/advanced-meta-data.html` |
| **flow: `on()`/`to()`, deciders, `end()`/`fail()`/`stopAndRestart()`** | `step/controlling-flow.html` |
| tasklet steps and `RepeatStatus` | `step/tasklet.html` |
| **the commit interval, and what a chunk actually commits** | `step/chunk-oriented-processing/commit-interval.html` |
| make a step restartable, `allowStartIfComplete`, start limits | `step/chunk-oriented-processing/restart.html` |
| skip and retry policy | `.../configuring-skip.html`, `.../retry-logic.html` |
| transaction attributes: propagation, isolation, timeout | `.../transaction-attributes.html` |
| step/chunk/item listeners | `.../intercepting-execution.html` |
| `@StepScope`, `@JobScope`, `#{jobParameters[...]}` | `step/late-binding.html` |
| ItemReader / ItemWriter contracts, `ItemStream` | `readers-and-writers/item-reader.html`, `-writer.html`, `item-stream.html` |
| **a rerunnable reader with no saved state — the process indicator** | `readers-and-writers/process-indicator.html` |
| database readers: cursor vs paging | `readers-and-writers/database.html` |
| write your own reader or writer | `readers-and-writers/custom.html` |
| what readers/writers already exist | `readers-and-writers/item-reader-writer-implementations.html`, `appendix.html` |
| **multi-threaded steps, partitioning, remote chunking** | `scalability.html` |
| the repeat/retry primitives underneath | `repeat.html`, `retry.html` |
| **testing: `JobLauncherTestUtils`, `@SpringBatchTest`, step scope in tests** | `testing.html` |
| idioms — restart, fixed-delay, staging table | `common-patterns.html` |
| messaging: job launch by message, remote workers | `spring-batch-integration.html` |
| **remote chunking / remote partitioning specifics** | `spring-batch-integration/externalizing-execution.html` |
| metrics, tracing, JFR | `spring-batch-observability/micrometer.html`, `jfr.html` |
| the `BATCH_*` tables | `schema-appendix.html` |
| terms | `glossary.html`, `faq.html` |

## Pages read in full, with what they settled

- **`whatsnew.html`** (2026-08-30) — `ResourcelessJobRepository` is the
  *deliberate* default since 5.2, not an omission; **`@EnableJdbcJobRepository`**
  is the intended way to get a JDBC one; `JobOperator` now extends `JobLauncher`;
  `JobRepository` extends `JobExplorer`; `ChunkOrientedStep` replaces
  `ChunkOrientedTasklet`/`TaskletStep`; retry moved to Spring Framework 7's
  implementation; JUnit 4 support in `spring-batch-test` deprecated.
- **`readers-and-writers/process-indicator.html`** (2026-08-30) — the named
  pattern for a rerunnable reader: a marker column plus `saveState(false)`.
- **`step/controlling-flow.html`** (2026-08-30) — `ExitStatus` is what `on()`
  matches; `end()` makes the instance unrestartable, `fail()` does not.
- **`spring-batch-integration/externalizing-execution.html`** (2026-08-30) —
  documents **only** a manager-side `setReceiveTimeout`. Nothing on worker death,
  message loss, durability or reassignment.

Add a line here when you read a page in full, with the date and what it settled.
A page nobody has opened is a link; a page someone has read is a reference.
