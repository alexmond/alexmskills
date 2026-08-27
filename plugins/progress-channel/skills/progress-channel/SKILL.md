---
name: progress-channel
description: One visible channel for every long-running process — local sweeps, backgrounded commands, and work handed to external systems (a CI run, a media-server queue, a long download). Registers each as a row in a per-machine SQLite store with learned ETAs, pre-start duration forecasts, and stall/orphan detection from each job's own history. Use when starting any operation expected to exceed ~10 seconds, when backgrounding a command, when triggering work in another system, or when the user asks "are we there yet", "how long will this take", "what's still running", or "track this progress".
---

# progress-channel

Work that takes minutes is usually reported by whatever the agent happens to
print — a carriage-returned counter in one terminal. That fails three ways:
the only way to learn the state is to re-ask (pure overhead), the counter can
lie (a stale fragment reads as a stall; submission-order iteration pins it at
0), and work handed to another system has no representation at all. This
skill makes a shared progress channel the default for all three.

## The discipline

- **Register anything expected to exceed ~10s** — a sweep, a backgrounded
  command, a call that hands work to another system and returns early.
  `progress forecast <name>` answers "how long has this taken before" *prior*
  to starting; if history says minutes, register.
- **Never answer a progress question by re-polling and narrating.** The
  answer is the channel: run `list` once, or point at `watch`. Register, then
  get on with something else.
- **External work gets a `mirror` watcher** — one small process polling the
  foreign system and writing its numbers into the same table, exiting when
  the work is idle. One list, whatever the source.

## Store

One dedicated SQLite file (WAL) at `~/.claude/progress/jobs.db` — per
machine, so every job on the box lands in one list; a `project` column keeps
per-repo filtering a query. It is deliberately **not** shared with any
application's own database (a long write transaction in a shared file
deadlocks; WAL permits one writer). `$PROGRESS_DB` overrides the path
(harness/tests). Finished rows auto-prune after 7 days; duration history
keeps the last 20 runs per job shape.

## Library

```python
# <plugin>/scripts/progress.py — stdlib only; import via the plugin path
with Job('video integrity', total=10453) as j:
    for item in items:
        j.step(detail=item, ok=1)        # or truncated=1, unreadable=1, ...
```

- The job is a **context manager**: an exception records `failed` with the
  error; only a SIGKILL-class death leaves a `running` row, and the viewer
  catches those by pid liveness. Never write to the table without it.
- `step()` accepts categorical counters (`ok=812 truncated=3`) — sweep
  output is categorical, and forcing it into per-project columns is what
  stops a channel from being generic.
- Writes are **throttled** (every 50 steps or 1s, plus on exit) — a 10k-item
  loop is a handful of transactions, not 10k.
- `set_total(n)` when the size is discovered mid-run; omit `total` when
  genuinely unknown (the view shows a count, not a lying percentage).

## CLI

```bash
python3 <plugin>/scripts/progress.py list [--all]      # one-shot view
python3 <plugin>/scripts/progress.py watch             # live TUI (ANSI redraw)
python3 <plugin>/scripts/progress.py forecast <name>   # pre-start estimate
python3 <plugin>/scripts/progress.py run --name build --total 1 -- make all
python3 <plugin>/scripts/progress.py mirror --name 'immich metadata' \
    --source immich-jobs --poll-cmd '<status cmd>' --interval 30
python3 <plugin>/scripts/progress.py prune [--days 7]
```

`run` wraps any command as a job (duration feeds the forecast even without
per-item granularity). `mirror`'s `--poll-cmd` is a user-supplied shell
command printing `<done> <total>`, `<done>`, or `idle`; the watcher exits
after `--idle-after` consecutive idle polls, and the running row itself is
the lease — a second mirror for the same `--source` refuses to start while
the first is alive.

## What the view tells you (and why to trust it)

The viewer never takes `running` at face value — that is how counters lie:

- **orphaned** ☠ — the row says running but its pid is dead on this host
  (killed too hard for the context manager). The next run of the same name
  also adjudicates its dead predecessors.
- **stalled** ⏸ — silent longer than 3× the job's *own* learned p95
  inter-step gap (never under 30s). A job whose gaps are always long is not
  stalled — that is exactly why the threshold is learned per job, and why a
  job with no history is never called stalled.
- **eta** — before ~10% progress the estimate comes from the median per-item
  rate of past runs of the same shape (name + kind + order-of-magnitude of
  total, so videos and thumbnails under one name don't blend); past it, the
  current run's own observed rate takes over. First run of a shape shows no
  estimate rather than extrapolating.

## Verify it's working

`python3 <plugin>/scripts/test-harness.py` (23 checks, throwaway store) —
or register a trivial job and confirm `list` shows it: the row appears at
registration, not completion.
