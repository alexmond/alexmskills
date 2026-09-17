#!/usr/bin/env python3
"""InstructionsLoaded hook: record which instruction files actually loaded.

Every other check in this plugin reasons about what the file SAYS. This one
records what the harness actually DID: which CLAUDE.md / .claude/rules files
were loaded into context, when, and why (`load_reason` is one of
session_start, nested_traversal, path_glob_match, include, compact).

Two questions become answerable that were previously guesswork, and both are
failure modes nothing else in the plugin can see:

  * A rule file that never loads. Path-scoped rules only load when Claude
    reads a matching file; one whose globs never match is pure repo weight
    that no audit of its CONTENT could ever flag, because the content is
    fine — it is the matching that is dead.
  * An instruction file that never loads at all. Claude Code loads a
    CLAUDE.md up to 4 MiB and SKIPS a larger one; a file in the wrong place
    is skipped just as silently. Either way the repo looks configured and
    isn't, and the only honest evidence is the absence of a load event.

Writes newline-delimited JSON to .claude/evolving-claude-md/loads.jsonl,
capped at LOAD_KEEP records (a rolling window, not an archive — this is an
audit input, exactly like history in the progress channel). Never blocks,
never raises: a recorder that can break a session start is worse than no
recorder at all.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

STATE_DIR = os.path.join(".claude", "evolving-claude-md")
LOADS = os.path.join(STATE_DIR, "loads.jsonl")
LOAD_KEEP = 400          # ~ dozens of sessions; rewritten in place when over


def _paths(payload: dict) -> list[str]:
    """Every shape the event might name a file in, without guessing a schema."""
    out: list[str] = []
    for key in ("file_path", "filePath", "path", "file", "files", "paths"):
        val = payload.get(key)
        if isinstance(val, str):
            out.append(val)
        elif isinstance(val, list):
            out.extend(str(v) for v in val if isinstance(v, (str, int)))
    return [p for p in dict.fromkeys(out) if p]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
        if payload.get("cwd"):
            os.chdir(payload["cwd"])
        record = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "session": payload.get("session_id") or "",
            # The matcher field. Absent on clients that do not send it, which
            # is fine: the file list is what the checks actually read.
            "reason": payload.get("load_reason") or payload.get("loadReason") or "",
            "files": _paths(payload),
        }
        if not record["files"]:
            return 0                      # nothing to learn from an empty event
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(LOADS, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        # Trim in place once it drifts past the cap. Cheap: this file is one
        # short line per load event, and the trim runs only when over.
        try:
            with open(LOADS, encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
            if len(lines) > LOAD_KEEP * 2:
                tmp = LOADS + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    fh.writelines(lines[-LOAD_KEEP:])
                os.replace(tmp, LOADS)
        except OSError:
            pass
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
