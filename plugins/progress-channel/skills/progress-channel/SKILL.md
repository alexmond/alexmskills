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
python3 <plugin>/scripts/progress.py list              # one-shot view (all states)
python3 <plugin>/scripts/progress.py watch             # live TUI
python3 <plugin>/scripts/progress.py forecast <name>   # pre-start estimate
python3 <plugin>/scripts/progress.py run --name build --total 1 -- make all
python3 <plugin>/scripts/progress.py mirror --name 'immich metadata' \
    --source immich-jobs --poll-cmd '<status cmd>' --interval 30
python3 <plugin>/scripts/progress.py daemon            # foreground (debug)
python3 <plugin>/scripts/statusline.py                # status-line rows (stdin: session JSON)
python3 <plugin>/scripts/progress.py prune             # compact history.jsonl + drop names idle >7d
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

## Scoping: whose job is this?

Every producer records the Claude Code session that owns it, for free —
Claude Code exports `CLAUDE_CODE_SESSION_ID` into every tool process, so
nothing has to be plumbed through. `CLAUDE_CODE_AGENT` (set only inside a
subagent) is recorded too, so a subagent's work shows under the session that
spawned it while still being attributable to the agent.

```bash
curl -s 'localhost:7717/jobs?session=<id>'    # one session's work
```

The page takes the same `?session=` parameter and its session column links to
it. Work started outside a session — cron, a bare shell — carries no session
and appears only in the unfiltered view; the filter is an exact match, because
a per-session view that quietly included machine-wide work would be worse than
useless.

## What `/jobs` returns, and for how long

**`/jobs` returns live work only.** That is the whole point of an ambient
surface: it answers "what is happening now", not "what has ever happened".

- `?state=all` — everything still retained
- `?state=done,failed` — an explicit comma-separated set
- absent — `running` + `stalled`, **plus** anything finished within the linger
  window, so a job is visibly seen reaching 100% instead of blinking out

Deliberate surfaces are not filtered: `list`, `watch` and the MCP
`progress_list` all ask for `?state=all`, because you went looking.

Two clocks, deliberately separate:

| | default | env | meaning |
|---|---|---|---|
| linger | 20 s | `PROGRESS_DONE_LINGER` | how long a finished row stays in the **live view** |
| removal | 24 h | `PROGRESS_FINISHED_HOURS` | when a done/failed row is **dropped** |
| orphan removal | 30 min | `PROGRESS_ORPHAN_MINUTES` | orphans are already dead — a shorter leash |
| hard cap | 60 | `PROGRESS_FINISHED_MAX` | bounds a pathological day |

## Time-based progress

Not all work counts items. A bar fills from the best evidence available, and
**says which**, so an estimate is never mistaken for a measurement:

| mode | fills against | when |
|---|---|---|
| `items` | `done/total` | a total is known — the only measured mode |
| `time` | elapsed / declared duration | `Job(expect_seconds=)` / `start --seconds` |
| `eta` | elapsed / median of this job's past runs | history exists for the name |
| `eta~` | elapsed / median of *similar* jobs' runs | name never ran, but its **stem** did |
| `creep` | `1-exp(-t/90)`, capped 95 % | nothing to measure against |

`eta~` is the borrowed estimate: the name is normalized to a stem (lowercase,
path-ish tokens dropped, digits stripped — `make /home/a` ≈ `make /home/b`,
still ≠ `pytest`) and matched against same-stem runs in the same project
first, then anywhere. History records carry `project`/`session`/`agent` for
this; matching uses only the stable keys (stem, project) — session ids are
recorded for audit, never matched on.

`time` and `eta` cap at 99 %: a job that overruns its estimate must not read as
finished, because that is exactly when you want to look at it. The page hatches
estimated bars; the status line prints the mode.

## Heartbeats: `ping` and the stopped watchdog

`step` advances a count and is throttled. **`ping` says "still alive" and always
posts immediately** — a heartbeat a throttle might swallow is not a heartbeat.

```bash
T=$($P start --name 'remote build' --seconds 300 --timeout 60)
while ...; do $P ping $T; done              # time-based: just a heartbeat
$P ping $T -n 5                              # or carry items along
$P ping $T --total 900 --seconds 600         # override the shape mid-run
```

`--timeout N` is a contract the producer opts into: **no step or ping for N
seconds and the job is declared `stopped`** and retired. This is for producers
whose pid says nothing useful — a remote job, a shell that forks, anything
polled rather than owned. It outranks the learned `stalled` heuristic, which
stays advisory and self-resolving.

## Status line (per-session, in the Claude Code window)

`scripts/statusline.py` ships with the plugin and puts this session's live work
in the Claude Code prompt:

```
⏳ research sweep      █████▌░░░░░░░░░░░░  31% 11/36 · ~7s left
⏳ remote build        ░░░░░░░░░░░░░░░░░░   0% time
⏳ explorer: scan repo █████████████▌░░░░  75% 6/8
```

The status line is the **only** surface in the Claude Code window a user script
can drive on its own schedule: `statusLine.refreshInterval` re-runs the command
on a timer (minimum 1 s). Tool stdout is a sanitised pipe with no terminal —
carriage returns, cursor control and even colour are stripped — so this is the
one place a live bar can go.

Use it as the whole status line, in `~/.claude/settings.json`:

```json
{"statusLine": {"type": "command",
                "command": "python3 <plugin>/scripts/statusline.py",
                "refreshInterval": 1}}
```

**`refreshInterval` is what makes it animate.** Without it the line repaints
only on events (a new assistant message, `/compact` finishing) and a running
job looks frozen.

Or append it to a status line you already have:

```python
spec = importlib.util.spec_from_file_location("pc", "<plugin>/scripts/statusline.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
rows = m.render(payload.get("session_id"))     # None when idle
if rows:
    lines.append(rows)
```

Rows are scoped to the session (server-side), capped at 3, and label subagent
work with the agent's name. Colour works here even though it is stripped from
tool output.

Two rules any replacement must keep:

- **never spawn the daemon** — producers do that; a status line that did would
  start daemons because somebody looked at their prompt
- **never block** — a 250 ms timeout and a silent failure, because a missing
  progress row is a far smaller problem than a frozen status line, which is
  usually carrying other information too

## Notifications

An executable at `~/.claude/progress/notify` is the entire configuration:
the daemon runs it detached on every `done` / `failed` / `orphaned` /
`stalled` transition (stalls fire once per episode; activity resets it),
with the event in env vars — `PROGRESS_EVENT`, `PROGRESS_NAME`,
`PROGRESS_STATUS`, `PROGRESS_ERROR`, `PROGRESS_SECONDS`, `PROGRESS_PROJECT`.
Point it at `notify-send`, an email sender, anything. The daemon never
waits on it and never fails because of it. No hook file, no notifications.

## MCP (sessions read the channel as tools)

`scripts/progress_mcp.py` is a stdio MCP server — a thin face on the same
daemon API: `progress_list`, `progress_forecast`, `progress_start`,
`progress_step`, `progress_finish`. Register it per project:

```json
{"mcpServers": {"progress": {"command": "python3",
    "args": ["<plugin>/scripts/progress_mcp.py"]}}}
```

## Advisory auto-registration (hook)

The plugin ships a `PreToolUse` hook on Bash that nudges — never rewrites —
when a command deserves tracking: either the channel's own history says
this command shape has a median over ~10s (the learned answer to "should
this be tracked"), or it matches a short list of famously long-running
commands / is being backgrounded. The suggestion names the exact `run`
wrapper to use; trivially short commands stay silent.

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

History keeps the last 20 runs per shape — an ETA input, not an archive —
and **forgets dead names**: a job name with no run in the last 7 days loses
every row (estimate, stall threshold, sparkline) at daemon startup, on a
daily sweep pass, and on `prune`. Per-name, not per-row, so one fresh run
keeps a job's whole learning window. `PROGRESS_HISTORY_DAYS` widens it for
monthly jobs.

**Upgrades restart the daemon by handshake**: `/health` reports the plugin
version, and a producer from a *newer* install asks the old daemon to
`/shutdown` (SIGTERM fallback for pre-0.4 daemons) and respawns the new
code — no stale daemon holds the port across a plugin update. Only strictly
newer evicts, so a dev checkout never bullies an installed daemon, and live
jobs survive because every producer re-registers on its next flush.
The page's history section adds per-job duration sparklines and a **trend**
tag ("slowing +40%") when recent same-shape runs drift from the older
baseline; `forecast` prints the same trend. `run` also tees the wrapped
command's last output lines into the row, so a failed job shows *why* on
the page.

## Verify it's working

`python3 <plugin>/scripts/test-harness.py` (44 checks: real daemon on an
ephemeral port, SIGKILL orphan sweep, restart re-registration, degraded
mode, shell start/step/finish, notify hook, trend, MCP handshake, advisory
hook) — or register a trivial job and open the page: the row appears at
registration, not completion.
