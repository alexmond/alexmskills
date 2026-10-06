#!/usr/bin/env python3
"""A Python producer: the Job context manager, with a sub-job.

    PROGRESS_LIB=<plugin>/scripts ./python_job.py
    ./python_job.py                 # no PROGRESS_LIB: runs untracked

`Job` is a context manager, so an exception reports the job as failed with the
error text and a normal exit reports it done. There is nothing to clean up by
hand. Flushes are throttled (every 50 steps or 1s), so a 10,000-item loop is a
handful of requests, not 10,000.
"""
import importlib.util
import os
import sys
import time
from contextlib import contextmanager

DELAY = float(os.environ.get("DELAY", "0.05"))


def load_job():
    """The plugin's Job class, or a stand-in that does nothing.

    Importing by path keeps this file free of any install step. The stand-in
    is what makes the tracker optional: the work below is written once and
    runs the same with or without it."""
    lib = os.environ.get("PROGRESS_LIB")
    if lib and os.path.isfile(os.path.join(lib, "progress.py")):
        spec = importlib.util.spec_from_file_location("progress", os.path.join(lib, "progress.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.Job

    class Untracked:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *exc): return False
        def step(self, *a, **k): pass
        def set_total(self, n): pass
        @contextmanager
        def child(self, *a, **k): yield Untracked()
    return Untracked


def main() -> int:
    Job = load_job()
    files = [f"clip-{n:02d}.mov" for n in range(1, 9)]

    with Job("python transcode", total=len(files)) as job:
        for name in files:
            # A sub-job: its own bar, nested under the parent's row.
            with job.child(f"encode {name}", total=4) as enc:
                for _ in range(4):
                    time.sleep(DELAY)              # ← the real work goes here
                    enc.step()
            # Counters are free-form: tally whatever the work produces.
            job.step(detail=name, ok=1)
    print(f"transcoded {len(files)} clips")
    return 0


if __name__ == "__main__":
    sys.exit(main())
