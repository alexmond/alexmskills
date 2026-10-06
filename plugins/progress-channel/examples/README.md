# Integration examples

Small, runnable producers for the progress channel. Each one is a complete
program: copy it, replace the `sleep` with your work, and it reports itself.

Every example runs the same **with or without** the channel. Unset
`PROGRESS_CLI` and they are plain scripts with no dependency — that is the
pattern to copy, because a progress bar is never worth a broken job.

```bash
export PROGRESS_CLI="python3 <plugin>/scripts/progress.py"   # the CLI
export PROGRESS_LIB="<plugin>/scripts"                       # for the Python library
python3 <plugin>/scripts/progress.py watch                   # in another terminal
```

| You have | Start from | It shows |
|---|---|---|
| a shell loop | [`bash-loop.sh`](bash-loop.sh) | start / step / finish, counters, failure with a reason |
| a multi-stage script | [`bash-pipeline.sh`](bash-pipeline.sh) | stages nested under a parent with one `export`; an unmodified sub-script nesting itself |
| Python | [`python_job.py`](python_job.py) | the `Job` context manager, sub-jobs, an untracked fallback |
| Node / TypeScript | [`node-job.mjs`](node-job.mjs) | calling the CLI from another language, batching steps |
| Go | [`go-job/main.go`](go-job/main.go) | the same three calls, a deferred finish that reports a panic |
| a Makefile | [`Makefile`](Makefile) | wrapping targets as timed jobs |
| a build or test tool | [`taps.md`](taps.md) | one pipe per tool: Maven, Gradle, Cargo, Go, pytest, Jest, Docker, Ninja, CMake, .NET, rsync, Terraform, Ansible |

## The contract, in any language

No library is needed. Anything that can start a process can be a producer:

```
start  --name <text> [--total N] [--pid PID]   → prints a token
step   <token> [-n N | --done N] [--total N] [--detail text] [--count key=N]
finish <token> [--fail "why" | --cancel]
```

Four things the examples do that are worth keeping:

1. **Close the job on every way out.** `trap … EXIT` in shell, a context
   manager in Python, `try/catch` in Node, `defer` in Go. A job nobody
   finished is swept as orphaned, but a failure with its reason is more use.
2. **Say who owns the job when you are not the direct caller.** The channel
   watches the process that started a job. From Node or Go, and from a shell
   function called inside `$( )`, that is a short-lived child — pass
   `--pid` with the pid of the long-lived process.
3. **Batch steps in a hot loop.** Each CLI call is a process. `step -n 50`
   every fifty items costs one call instead of fifty.
4. **Never let the tracker fail the work.** Every helper here swallows its
   own errors and returns an empty token, and every call is guarded on that
   token.

## Nesting

Export `PROGRESS_PARENT=<token>` and every job started below — by this
script, a sub-script, `progress run`, or a tap — nests under it. Nothing
else is passed around. `bash-pipeline.sh` runs `bash-loop.sh` unmodified as
its second stage to show exactly that.
