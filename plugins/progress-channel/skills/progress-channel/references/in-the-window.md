# Showing jobs in the Claude Code window

Two ways, and they do not overlap: the band's `auto` mode hides it while a
status line is polling the daemon.

## Status line

`scripts/statusline.py` ships with the plugin and puts this session's live work
in the Claude Code prompt:

```
⏳ research sweep      █████▌░░░░░░░░░░░░  31% 11/36 · ~7s left
⏳ remote build        ░░░░░░░░░░░░░░░░░░   0% time
⏳ explorer: scan repo █████████████▌░░░░  75% 6/8
```

The status line is the only surface in the Claude Code window a user *script*
can drive on its own schedule: `statusLine.refreshInterval` re-runs the command
on a timer (minimum 1 s). Tool stdout is a sanitised pipe with no terminal —
carriage returns, cursor control and even colour are stripped.

## The band above the prompt (0.7.0, Claude Code only)

The plugin also ships a **mod** (`hooks/register.tsx`) that draws the same rows
above the prompt. It needs no `settings.json` edit — it loads with the plugin —
and has room for six rows, with the bars in one column.

- `/progress-bar` toggles it; `on|off|auto` sets the mode, remembered across
  sessions.
- **`auto` is the default**: the band draws only while no status line is polling
  the daemon, so a job is never drawn twice.
- It only reads, locally, and never starts the daemon.

With no status line wired, point the user at the band first — it is already on.
Offer the status line for Codex, or where a mod cannot draw.

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

## Set the status line up on request

When the user asks to wire this up ("set up the progress status line", "show
progress in my status line"), do the edit for them — `~/.claude/settings.json`:

1. **No `statusLine` configured** → set it to `scripts/statusline.py` (absolute
   plugin path) with `"refreshInterval": 1`, as above.
2. **A status line already exists** → keep it and wrap it:
   `"command": "python3 <plugin>/scripts/statusline_wrap.py -- <their command>"`
   — runs their command unchanged and appends the progress rows.

Then tell the user to restart the session (settings load at startup). Whether a
renderer is actually wired is knowable without guessing: `/health` reports
`statusline_seen` — true once any status line has polled this daemon boot. The
live page shows a setup banner while it is false, the advisory nudge adds a
weekly tip, and the once-per-upgrade notice offers this setup — so if the user
seems unaware of the integration, offer it once.
