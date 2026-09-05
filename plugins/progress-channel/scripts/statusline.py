#!/usr/bin/env python3
"""Claude Code status-line renderer for the progress channel.

The status line is the only surface in the Claude Code window that a
user-authored script can drive on its own schedule: `statusLine.refreshInterval`
re-runs the command on a timer (minimum 1 second). Tool stdout is a sanitised
pipe with no terminal, so this is the one place a live bar can go.

Two ways to use it.

1. As the whole status line — add to ~/.claude/settings.json:

    "statusLine": {
      "type": "command",
      "command": "python3 <plugin>/scripts/statusline.py",
      "refreshInterval": 1
    }

2. Appended to a status line you already have — import and call render():

    import sys, importlib.util
    spec = importlib.util.spec_from_file_location("pcstatus", "<plugin>/scripts/statusline.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    rows = m.render(payload.get("session_id"))
    if rows:
        lines.append(rows)

`refreshInterval` is what makes it animate; without it the line only repaints
on events (a new assistant message, /compact finishing) and a running job will
look frozen.

Two rules this file keeps, and any replacement must keep:

  * NEVER spawn the daemon. Producers auto-spawn it. A status line that did the
    same would start daemons because somebody looked at their prompt.
  * NEVER block. It runs about once a second. A short timeout and a silent
    failure are correct — a missing progress row is a far smaller problem than
    a frozen status line, which is usually carrying other information too.

Filtering is done by the daemon (`/jobs?session=`), not here, so this and the
web page ask the same question and cannot drift apart.
"""
import json
import os
import sys
import urllib.parse
import urllib.request

TIMEOUT = 0.25          # seconds — never wait on a sick daemon
MAX_ROWS = 3            # never push the prompt off the screen
WIDTH = 18
_RAMP = " ▏▎▍▌▋▊▉█"    # 8 sub-steps per cell: at 1 fps, small moves stay visible

# Only live work belongs in a prompt. The daemon's default already excludes
# finished rows past the linger window; this is belt and braces so a future
# default change cannot quietly fill the line with history.
LIVE = ("running", "stalled")


def base_url() -> str:
    return "http://127.0.0.1:%s" % os.environ.get("PROGRESS_PORT", "7717")


def fetch(session_id=None):
    """Live jobs for this session, or [] for any failure at all."""
    url = base_url() + "/jobs"
    if session_id:
        url += "?session=" + urllib.parse.quote(str(session_id))
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            return (json.loads(r.read().decode()) or {}).get("jobs") or []
    except Exception:
        return []


def bar(ratio: float, width: int = WIDTH) -> str:
    ratio = max(0.0, min(1.0, ratio))
    exact = ratio * width
    full = int(exact)
    out = "█" * full
    if full < width:
        idx = int((exact - full) * (len(_RAMP) - 1))
        # Index 0 is a space, which reads as a hole punched in the bar.
        out += _RAMP[idx] if idx > 0 else "░"
        rest = width - full - 1
        if rest > 0:
            out += "░" * rest
    return out[:width]


def _dur(seconds) -> str:
    s = int(seconds or 0)
    if s < 60:
        return "%ds" % s
    if s < 3600:
        return "%dm%02ds" % divmod(s, 60)
    return "%dh%02dm" % (s // 3600, (s % 3600) // 60)


def render(session_id=None, width: int = WIDTH):
    """One row per live job in this session, or None when there is nothing.

    ANSI colour is supported on the status line (unlike tool output, which is
    stripped), so the rows are coloured: cyan running, yellow stalled.
    """
    jobs = [j for j in fetch(session_id) if j.get("state") in LIVE]
    rows = []
    for j in jobs[:MAX_ROWS]:
        ratio = j.get("progress")
        if ratio is None:
            continue
        mode = j.get("progress_mode") or "creep"
        stalled = j.get("state") == "stalled"
        name = str(j.get("name") or "job")[:26]

        # A subagent's job runs under this session and belongs in this line,
        # but it is not the main loop's work — say whose it is.
        if j.get("agent"):
            name = "%s: %s" % (str(j["agent"])[:10], name[:20])

        colour, mark = ("\033[33m", "!") if stalled else ("\033[36m", "⏳")

        # items is measured; time/eta/creep are estimates. Name the mode so an
        # estimated bar is never read as a counted one.
        if mode == "items":
            tail = "%s/%s" % (j.get("done", 0), j.get("total"))
        else:
            tail = mode
        if j.get("eta_seconds"):
            tail += " · ~%s left" % _dur(j["eta_seconds"])
        if stalled:
            tail += " · stalled"

        rows.append("%s%s %s\033[0m %s%s\033[0m %3d%% \033[2m%s\033[0m" % (
            colour, mark, name, colour, bar(ratio, width),
            int(round(ratio * 100)), tail))

    return "\n".join(rows) if rows else None


def main() -> int:
    # Claude Code pipes the session JSON in on stdin; tolerate being run by hand.
    session_id = None
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
        if raw.strip():
            session_id = (json.loads(raw) or {}).get("session_id")
    except Exception:
        pass
    if not session_id:
        session_id = os.environ.get("CLAUDE_CODE_SESSION_ID")

    out = render(session_id)
    if out:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
