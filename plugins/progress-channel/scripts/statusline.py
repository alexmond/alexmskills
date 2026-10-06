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
import re
import json
import os
import sys
import urllib.parse
import urllib.request

TIMEOUT = 0.25          # seconds — never wait on a sick daemon
MAX_ROWS = 3            # never push the prompt off the screen
MAX_BYTES = 1_000_000   # a real reply is a few KB; refuse anything absurd unread
MAX_JOBS = 200
MAX_TEXT = 80           # no printed field is longer than this, so none is scanned further
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
            # Bounded BEFORE it is parsed: a cap applied to the parsed list
            # has already paid for reading and decoding all of it.
            raw = r.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return []
        jobs = (json.loads(raw.decode()) or {}).get("jobs") or []
        return [_safe(j) for j in jobs[:MAX_JOBS] if isinstance(j, dict)]
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
    jobs = [j for j in fetch(session_id)
            if j.get("state") in LIVE and j.get("progress") is not None]
    units = _units(jobs)
    if not units:
        return None

    # Row budget. Every top-level job gets a row before any child does — a
    # second pipeline must not be pushed off the line by the first one's
    # step. Leftover rows go to children in order; a child that gets no row
    # is folded onto its parent's line instead of disappearing. A child row
    # is only ever emitted directly under its parent's, so an arrow never
    # points at nothing.
    units = units[:MAX_ROWS]
    spare = MAX_ROWS - len(units)
    rows = []
    for root, kids in units:
        shown, folded = kids[:spare], kids[spare:]
        spare -= len(shown)
        rows.append(_row(root, width, folded=folded))
        for k in shown:
            rows.append(_row(k, width, child=True))
    return "\n".join(rows)


def _units(jobs):
    """[(root, [children…])] in the daemon's tree order.

    The daemon orders rows as a tree and sets `depth`; this only groups them.
    Direct children get rows; anything deeper is folded into its depth-1
    ancestor's line by being dropped from the row list (its fraction already
    reached the parent through the daemon's rollup). A child whose parent is
    not in this view — filtered out, or ended — is treated as a root rather
    than drawn under the wrong row.
    """
    present = {j.get("uid") for j in jobs}
    units = []
    for j in jobs:
        depth = int(j.get("depth") or 0)
        if depth == 0 or j.get("parent") not in present or not units:
            units.append((j, []))
        elif depth == 1:
            units[-1][1].append(j)
    return units


_UNSAFE = re.compile(
    "[\\x00-\\x1f\\x7f-\\x9f\\u200b-\\u200f\\u2028-\\u202e\\u2066-\\u2069\\ufeff]")


def _clean(v) -> str:
    """Any process on the machine can register a job, so a name is untrusted
    text about to be printed where ANSI is live. Control characters go — an
    escape sequence could recolour or overwrite the prompt — and so do the
    bidi and zero-width marks that make text read as something it is not."""
    # Cut first, then scan: the other order runs the pattern over the whole of
    # a megabyte-long name to keep eighty characters of it. Every replacement
    # is one character for one, so the cut length holds.
    return _UNSAFE.sub(" ", str(v or "")[:MAX_TEXT])


def _num(v, lo=0, hi=10 ** 12):
    """A number inside [lo, hi], or None. Finite is not enough: Python ints
    have no upper limit, so a `done` of 10**5000 is a valid number that prints
    as five thousand digits, and a progress of 1e308 overflows the percent.
    Out of range is refused, not clamped — a nonsense count should not be
    drawn as a plausible one. bool is an int in Python; it is not a count."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    if v != v or not lo <= v <= hi:
        return None
    return v


# Each number with the range it can honestly have.
_NUM_RANGE = {"progress": (0, 1), "done": (0, 10 ** 12), "total": (0, 10 ** 12),
              "eta_seconds": (0, 10 ** 9), "depth": (0, 64)}


_TEXT = ("uid", "name", "state", "progress_mode", "parent", "agent", "detached")
_NUMS = ("progress", "done", "total", "eta_seconds", "depth")


def _safe(j: dict) -> dict:
    """One job with EVERY field that reaches the screen checked — not only the
    name. `done`, `total` and the mode are printed too, and a producer that
    posts straight to the daemon can put text in any of them."""
    out = {k: (_clean(j.get(k)) if isinstance(j.get(k), str) else None)
           for k in _TEXT}
    out.update({k: _num(j.get(k), *_NUM_RANGE[k]) for k in _NUMS})
    return out


def _row(j, width, child=False, folded=()):
    j = _safe(j)
    folded = [_safe(f) for f in folded]
    ratio = j["progress"] or 0
    mode = j.get("progress_mode") or "creep"
    stalled = j.get("state") == "stalled"
    if child:
        name = "  ↳ " + str(j.get("name") or "job")[:22]
    else:
        name = str(j.get("name") or "job")[:26]

    # A subagent's job runs under this session and belongs in this line,
    # but it is not the main loop's work — say whose it is.
    if j.get("agent") and not child:
        name = "%s: %s" % (str(j["agent"])[:10], name[:20])

    colour, mark = ("\033[33m", "!") if stalled else ("\033[36m", "⏳")

    # items (and items+sub, a count plus measured children) are measured;
    # time/eta/creep are estimates. Name the mode so an estimated bar is never
    # read as a counted one.
    if mode in ("items", "items+sub"):
        tail = "%s/%s" % (j.get("done") or 0, j.get("total"))
    else:
        tail = mode
    if j.get("eta_seconds"):
        tail += " · ~%s left" % _dur(j["eta_seconds"])
    if stalled:
        tail += " · stalled"
    if j.get("detached"):
        tail += " · " + str(j["detached"])[:30]
    if folded:
        f = folded[0]
        tail += " · ↳ %s %d%%" % (str(f.get("name") or "")[:18],
                                   int(round((f.get("progress") or 0) * 100)))
        if len(folded) > 1:
            tail += " +%d" % (len(folded) - 1)

    return "%s%s %s\033[0m %s%s\033[0m %3d%% \033[2m%s\033[0m" % (
        colour, mark, name, colour, bar(ratio, width),
        int(round(ratio * 100)), tail)


def main() -> int:
    # Claude Code pipes the session JSON in on stdin; tolerate being run by hand.
    session_id = None
    try:
        raw = sys.stdin.read(MAX_BYTES) if not sys.stdin.isatty() else ""
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
