#!/usr/bin/env python3
"""Status-line wrapper: run the user's existing status-line command, then
append this session's progress rows under it.

The docs' "append it to a status line you already have" pattern required
writing Python. This makes it a one-line settings change instead — wrap
whatever command is already there:

    {"statusLine": {"type": "command",
                    "command": "python3 <plugin>/scripts/statusline_wrap.py -- <your command>",
                    "refreshInterval": 1}}

With no wrapped command it degrades to the plain renderer, so it is also a
safe default target.

Contract (same as any status line): never block, never fail — the wrapped
command gets a short timeout, the progress rows have their own, and any
failure just means that half of the line is missing this refresh."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

WRAPPED_TIMEOUT = 4.0


def main() -> int:
    raw = sys.stdin.buffer.read()   # Claude Code's session JSON, passed through

    argv = sys.argv[1:]
    if argv and argv[0] == "--":
        argv = argv[1:]

    if argv:
        try:
            out = subprocess.run(argv, input=raw, capture_output=True,
                                 timeout=WRAPPED_TIMEOUT).stdout
            if out.strip():
                sys.stdout.buffer.write(out.rstrip(b"\n") + b"\n")
        except Exception:
            pass   # the wrapped half is missing this refresh; rows still print

    try:
        session_id = (json.loads(raw or b"{}") or {}).get("session_id")
    except Exception:
        session_id = None
    try:
        spec = importlib.util.spec_from_file_location(
            "pc_statusline",
            Path(__file__).resolve().parent / "statusline.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        rows = mod.render(session_id)
        if rows:
            print(rows)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
