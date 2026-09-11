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

Patterns:
    maven  (default)   reactor line [3/15] — absolute position, count is SET
    git                clone/fetch phase lines — per-phase done/total
    batch              Spring Batch step lines — counts steps, total unknown
    count:<regex>      count matching lines; --total declares the denominator

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
    # Spring Batch prints one per step; no denominator, so it counts.
    "batch": r"(?:Executing step|Step:\s*\[)\s*(?P<name>[^\]\s][^\]]*)",
}

# git can emit hundreds of \r updates per second; one subprocess per update
# would cost more than the clone. Same-shape updates are throttled; a phase
# change or a new total always posts, so the bar never lies across phases.
POST_MIN_INTERVAL = 1.0


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

    rx_src = PATTERNS.get(pattern) or (
        pattern[len("count:"):] if pattern.startswith("count:")
        else PATTERNS["maven"])
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
                m = rx.search(line)
                if not m:
                    continue
                g = m.groupdict()
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
