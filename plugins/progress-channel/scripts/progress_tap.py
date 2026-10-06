#!/usr/bin/env python3
"""Pipe filter: forward stdin unchanged, report its progress to the channel.

Why a tap and not `progress.py run`: that wrapper times an opaque command and
shows one featureless bar. Build tools already print the real position —

    [INFO] Building acme-core 1.4.0-SNAPSHOT                    [3/15]   (maven)
    Receiving objects:  42% (12345/29292)                                (git)

— done AND total, both free, so the bar is MEASURED rather than estimated.
It was already going into a log nobody watches; this reads it in passing.

Generalized from venice-vr's scripts/progress-tap.py (gate.sh's pipe filter,
production-proven across gate/merge-check/test-affected), with two changes:
progress.py is resolved next to this file instead of a pinned plugin-cache
path, and parsing is carriage-return-aware — git emits progress as `\\r`
updates on one line, which a `for line in stdin` reader would buffer until
the clone finished.

Transparency contract (why callers can trust it in a verdict pipeline):
stdin is copied to stdout byte-for-byte, nothing is written to stdout that
did not arrive on stdin, and every progress call is best-effort — daemon
down, plugin moved, python broken: the build still runs and still reports.
Degradation is silent because a WARNING on every build is its own defect.

THE CALLER STILL OWNS THE EXIT CODE. A pipeline's `$?` is the LAST command's
— this tap's. Read `${PIPESTATUS[0]}`.

    mvn -B verify 2>&1              | progress_tap.py "gate: full" > build.log
    git clone --progress <url> 2>&1 | progress_tap.py "clone linux" --pattern git
    tool 2>&1 | progress_tap.py migrate --pattern 'count:^migrated' --total 800

git only prints progress when stderr is a tty OR --progress is forced —
in a pipe, always pass --progress and merge stderr (2>&1).

Patterns — three kinds, by what the tool prints:

  measured (done AND total on the line; the bar is exact)
    maven  (default)   reactor line [3/15]
    git                clone/fetch phase lines — per-phase done/total
    docker             BuildKit `#7 [build 3/9] RUN …` and legacy `Step 3/9 :`
    ninja              `[12/345] Building …` (also Bazel, Meson, anything on Ninja)
    ratio              any `N/M` on the line — the generic form of the four above

  percent (the tool prints a percentage; the bar is its own number)
    pytest             `tests/test_x.py ....   [ 42%]`
    cmake              `[ 42%] Building CXX object …` (CMake's Makefile generator)
    rsync              `--info=progress2` overall percentage
    percent            any `NN%` on the line — the generic form

  counted (one line per finished unit; no denominator unless --total gives one)
    gradle             `> Task :app:compileJava` (run Gradle with --console=plain)
    cargo              `Compiling serde v1.0.203`
    go                 `ok  example.com/pkg  0.41s` — one per package
    jest               `PASS src/x.test.ts` — one per test file (Jest and Vitest)
    dotnet             `App.Core -> /…/App.Core.dll` — one per project
    terraform          `aws_instance.web: Creation complete`
    ansible            `TASK [install packages] ***`
    batch              Spring Batch step lines
    count:<regex>      count lines matching your own regex

A counted bar has no percentage until it has a total. Give it one when you can
(`--total "$(go list ./... | wc -l)"`); otherwise the channel shows the count
and, from the second run, an estimate learned from the first.

Options: --pattern <name> · --total <n> · --timeout <secs> · --quiet (pure cat)
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

PROG = str(Path(__file__).resolve().parent / "progress.py")

PATTERNS = {
    # Absolute position: "Building <name> ... [3/15]" -> (done, total, name).
    "maven": r"Building\s+(?P<name>.*?)\s+\S+\s+\[(?P<done>\d+)/(?P<total>\d+)\]",
    # git clone/fetch/checkout phases, each measured on its own denominator.
    "git": (r"(?P<name>Counting objects|Compressing objects|Receiving objects|"
            r"Resolving deltas|Updating files|Checking out files)"
            r":\s+\d+%\s+\((?P<done>\d+)/(?P<total>\d+)\)"),
    # BuildKit plain output "#7 [build 3/9] RUN make" and legacy "Step 3/9 : RUN".
    "docker": (r"(?:^#\d+\s+\[(?:[\w.-]+\s+)?|^Step\s+)(?P<done>\d+)/(?P<total>\d+)\]?"
               r"\s*:?\s*(?P<name>.*)"),
    # Ninja, and everything that drives it: "[12/345] Building CXX object …".
    "ninja": r"^\[(?P<done>\d+)/(?P<total>\d+)\]\s*(?P<name>.*)",
    # The generic measured form, for a tool with no preset.
    "ratio": r"(?<![\d./])(?P<done>\d+)\s*/\s*(?P<total>\d+)(?![\d./])",

    # Percent patterns: the tool states its own percentage. `pct` is read as
    # done-of-100.
    "pytest": r"\[\s*(?P<pct>\d{1,3})%\]\s*$",
    "cmake": r"^\[\s*(?P<pct>\d{1,3})%\]\s+(?P<name>.*)",
    # rsync --info=progress2: "  1,234,567  42%  1.23MB/s    0:00:12"
    "rsync": r"^\s*[\d,]+\s+(?P<pct>\d{1,3})%\s",
    "percent": r"(?<![\d.])(?P<pct>\d{1,3})%",

    # Counted patterns: one line per finished unit, no denominator.
    "gradle": r"^> Task (?P<name>:\S+)",
    "cargo": r"^\s*Compiling\s+(?P<name>\S+)",
    "go": r"^(?:ok|FAIL|---\s+FAIL:)\s+(?P<name>\S+)",
    # Jest prints PASS/FAIL per file; Vitest prints a tick or cross.
    "jest": r"^\s*(?:PASS|FAIL|[\u2713\u2714\u00d7\u2717])\s+(?P<name>\S+\.[cm]?[jt]sx?)\b",
    "dotnet": r"^\s*(?P<name>\S+)\s+->\s+\S+\.(?:dll|exe)\s*$",
    "terraform": r"^(?P<name>\S+): (?:Creation|Modifications|Destruction) complete",
    "ansible": r"^TASK \[(?P<name>[^\]]+)\]",
    # Spring Batch prints one per step; no denominator, so it counts.
    "batch": r"(?:Executing step|Step:\s*\[)\s*(?P<name>[^\]\s][^\]]*)",
}

# git can emit hundreds of \r updates per second; one subprocess per update
# would cost more than the clone. Same-shape updates are throttled; a phase
# change or a new total always posts, so the bar never lies across phases.
POST_MIN_INTERVAL = 1.0


# A progress line is short. Anything longer is a minified bundle or a base64
# blob on one line; matching a backtracking regex against megabytes of it is
# how a pipe filter stalls a build.
MAX_LINE = 2000
# Counts beyond this are not counts. It also keeps int() far below Python's
# digit limit, past which it raises.
MAX_DIGITS = 12


def _position(rx, line: str):
    """One line → its position groups, or None when it carries none.

    Returns a dict where `done`/`total`, if present, are digit strings short
    enough to be real counts."""
    m = rx.search(line)
    if not m:
        return None
    g = {k: v for k, v in m.groupdict().items() if v is not None}
    if "pct" in g:
        # A stated percentage is done-of-100. Above 100 it is not a progress
        # figure ("250% of quota").
        if not g["pct"].isdigit() or int(g["pct"]) > 100:
            return None
        g["done"], g["total"] = g["pct"], "100"
    for k in ("done", "total"):
        if k in g and not (g[k].isdigit() and len(g[k]) <= MAX_DIGITS):
            return None
    return g


def parse_args(argv):
    name = "build"
    if argv and not argv[0].startswith("--"):
        name, argv = argv[0], argv[1:]
    pattern, total, timeout, quiet = "maven", None, None, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--pattern" and i + 1 < len(argv):
            pattern, i = argv[i + 1], i + 2
        elif a == "--total" and i + 1 < len(argv):
            total, i = argv[i + 1], i + 2
        elif a == "--name" and i + 1 < len(argv):
            name, i = argv[i + 1], i + 2
        elif a == "--timeout" and i + 1 < len(argv):
            timeout, i = argv[i + 1], i + 2
        elif a == "--quiet":
            quiet, i = True, i + 1
        else:
            i += 1
    return name, pattern, total, timeout, quiet


def passthrough() -> int:
    """Be a plain `cat`. The one job that must never fail."""
    while True:
        chunk = sys.stdin.buffer.read(65536)
        if not chunk:
            break
        sys.stdout.buffer.write(chunk)
        sys.stdout.buffer.flush()
    return 0


def post(args) -> None:
    """Best-effort call into the channel; never raises, never blocks long."""
    try:
        subprocess.run([sys.executable, PROG, *args], timeout=5,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def main() -> int:
    name, pattern, total, timeout, quiet = parse_args(sys.argv[1:])

    if quiet or not os.path.isfile(PROG):
        return passthrough()

    if pattern.startswith("count:"):
        rx_src = pattern[len("count:"):]
    elif pattern in PATTERNS:
        rx_src = PATTERNS[pattern]
    else:
        # An unknown name used to fall back to the Maven pattern, which
        # matches nothing in anyone else's output and looks like a stuck job.
        # Say so once on stderr — stdout stays byte-for-byte — and still run.
        print(f"progress_tap: unknown pattern {pattern!r}; known: "
              f"{', '.join(sorted(PATTERNS))}, count:<regex>. Tracking the "
              f"job with no position.", file=sys.stderr)
        rx_src = r"(?!)"
    try:
        rx = re.compile(rx_src)
    except re.error:
        return passthrough()

    start = ["start", "--name", name, "--pid", str(os.getppid())]
    if total:
        start += ["--total", total]
    if timeout:
        start += ["--timeout", timeout]
    try:
        token = subprocess.run([sys.executable, PROG, *start], timeout=10,
                               capture_output=True, text=True).stdout.strip()
    except Exception:
        token = ""
    if not token:
        return passthrough()

    done, failed = 0, None
    last_post, last_shape = 0.0, None
    carry = ""      # text tail since the last \r or \n, for parsing only
    try:
        while True:
            chunk = sys.stdin.buffer.read(65536)
            if not chunk:
                break
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
            carry += chunk.decode("utf-8", "replace")
            # \r-separated updates (git) parse like lines; keep the tail.
            parts = re.split(r"[\r\n]", carry)
            carry = parts.pop()[-4096:]
            for line in parts:
                # The pipe has already been forwarded above. Nothing a line
                # contains may stop the next chunk from being forwarded too:
                # a count too long for int(), a user regex that names a group
                # `done` and captures text, a pathological match. Reading
                # position is optional; being a pipe is not.
                try:
                    g = _position(rx, line[:MAX_LINE])
                except Exception:
                    g = None
                if g is None:
                    continue
                detail = (g.get("name") or line.strip())[:60]
                if g.get("done") and g.get("total"):
                    # SET, don't increment: a resumed or -T reactor does not
                    # emit one line per module in order, and git repeats the
                    # same phase at rising percentages.
                    done = int(g["done"])
                    shape = (detail, g["total"])
                    now = time.time()
                    final = done == int(g["total"])
                    if (shape != last_shape or final
                            or now - last_post >= POST_MIN_INTERVAL):
                        last_shape, last_post = shape, now
                        post(["step", token, "--done", str(done),
                              "--total", g["total"], "--detail", detail])
                else:
                    done += 1
                    post(["step", token, "--done", str(done),
                          "--detail", detail])
    except BrokenPipeError:
        # The reader went away. Still finish the row: a job left "running"
        # is exactly the dead-bar-that-lies the channel exists to remove.
        failed = "downstream closed the pipe"
    except KeyboardInterrupt:
        failed = "interrupted"
    finally:
        try:
            sys.stdout.buffer.flush()
        except Exception:
            pass
        post(["finish", token] + (["--fail", failed] if failed else []))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        os._exit(0)
