---
name: progress-channel
description: One visible channel for every long-running process — local sweeps, backgrounded commands, and work handed to external systems (a CI run, a media-server queue, a long download). The server that serves the live progress page IS the tracker — a stdlib Python daemon holding live jobs in memory, auto-spawned by the first producer — with learned ETAs, pre-start duration forecasts, and stall/orphan detection from each job's own history. Use when starting any operation expected to exceed ~10 seconds, when backgrounding a command, when triggering work in another system, or when the user asks "are we there yet", "how long will this take", "what's still running", or "track this progress".
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
  answer is the channel: the live page at `http://127.0.0.1:7717/`, `watch`
  in a terminal, or `list` once. Register, then get on with something else.
- **External work gets a `mirror` watcher** — one small process polling the
  foreign system into the same channel, exiting when the work is idle. One
  list, whatever the source.

## Architecture

The thing that serves the progress page **is** the tracker. A stdlib-only
Python daemon (`http.server`, no dependencies) binds `127.0.0.1:7717`
(`$PROGRESS_PORT` overrides), holds live jobs **in memory** — single writer,
so there is no store or locking at all — and serves the HTML view at `/`,
JSON at `/jobs`, and forecasts at `/forecast?name=`.

- **Producers auto-spawn it**: the first `Job` brings the daemon up if it
  isn't running; binding the port is the single-instance lease. Nothing to
  install or supervise.
- **Only the learning data is persisted**: finished runs append to
  `~/.claude/progress/history.jsonl` (`cat`/`jq`-able; `$PROGRESS_HOME`
  overrides the directory). Live state is memory-only on purpose — if the
  daemon restarts, producers re-register on their next flush; a reboot kills
  the jobs anyway.
- **A job never fails because the tracker is sick**: if the daemon can't be
  reached or spawned, the job degrades to a warn-once untracked no-op.

## Library

```python
# <plugin>/scripts/progress.py — stdlib only; import via the plugin path
with Job('video integrity', total=10453) as j:
    for item in items:
        j.step(detail=item, ok=1)        # or truncated=1, unreadable=1, ...
```

- The job is a **context manager**: an exception reports `failed` with the
  error; only a SIGKILL-class death goes silent, and the daemon's sweep
  catches those by checking the producer's pid directly (it is local — no
  heartbeat protocol). Never report progress around it.
- `step()` accepts categorical counters (`ok=812 truncated=3`) — sweep
  output is categorical, and forcing it into fixed fields is what stops a
  channel from being generic.
- Flushes are **throttled** (every 50 steps or 1s, plus on exit) — a
  10k-item loop is a handful of POSTs, not 10k.
- `set_total(n)` when the size is discovered mid-run; omit `total` when
  genuinely unknown (the view shows a count, not a lying percentage).

## CLI

```bash
python3 <plugin>/scripts/progress.py list              # one-shot view
python3 <plugin>/scripts/progress.py watch             # live TUI
python3 <plugin>/scripts/progress.py forecast <name>   # pre-start estimate
python3 <plugin>/scripts/progress.py run --name build --total 1 -- make all
python3 <plugin>/scripts/progress.py mirror --name 'immich metadata' \
    --source immich-jobs --poll-cmd '<status cmd>' --interval 30
python3 <plugin>/scripts/progress.py daemon            # foreground (debug)
python3 <plugin>/scripts/progress.py prune             # compact history.jsonl
```

`run` wraps any command as a job (duration feeds the forecast even without
per-item granularity). `mirror`'s `--poll-cmd` is a user-supplied shell
command printing `<done> <total>`, `<done>`, or `idle`; the watcher exits
after `--idle-after` consecutive idle polls, and its live job is the lease —
a second mirror for the same `--source` refuses to start while the first is
alive.

## From any script: start / step / finish

Anything that can run a command can be a producer — no Python import needed:

```bash
P='python3 <plugin>/scripts/progress.py'
T=$($P start --name 'photo import' --total 800)
trap '$P finish $T --fail "aborted at $f"' ERR
for f in *.jpg; do
    convert "$f" ...
    $P step $T --count ok=1 --detail "$f"     # -n N, --done N, --total N
done
$P finish $T                                   # or: --fail "why" / --cancel
```

`start` prints a token; the cross-invocation state (count, counters, step
gaps) lives in a token file under `~/.claude/progress/tokens/`, so `step` is
stateless for the script and keeps the same 1s POST throttle as the library.
Liveness anchors to the **calling script's pid** (`--pid` overrides), so a
script that dies without `finish` is swept as orphaned like any other
producer.

## What the view tells you (and why to trust it)

The viewer never takes `running` at face value — that is how counters lie:

- **orphaned** ☠ — the producer's pid is dead (killed too hard for the
  context manager). The daemon's sweep adjudicates these actively.
- **stalled** ⏸ — silent longer than 3× the job's *own* learned p95
  inter-step gap (never under 30s). A job whose gaps are always long is not
  stalled — that is exactly why the threshold is learned per job, and why a
  job with no history is never called stalled.
- **eta** — before ~10% progress the estimate comes from the median per-item
  rate of past runs of the same shape (name + kind + order-of-magnitude of
  total, so videos and thumbnails under one name don't blend); past it, the
  current run's own observed rate takes over. First run of a shape shows no
  estimate rather than extrapolating.

History keeps the last 20 runs per shape — an ETA input, not an archive.

## Verify it's working

`python3 <plugin>/scripts/test-harness.py` (34 checks: real daemon on an
ephemeral port, SIGKILL orphan sweep, restart re-registration, degraded
mode, shell start/step/finish) — or register a trivial job and open the
page: the row appears at registration, not completion.
