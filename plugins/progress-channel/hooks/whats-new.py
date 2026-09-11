#!/usr/bin/env python3
"""SessionStart hook: one notice per install or upgrade, never more.

Claude Code has no install/upgrade hook, so the plugin detects the
transition itself: the hook runs from the versioned cache path, so its own
plugin_version() is the truth, and a last-version marker in the writable
state dir (~/.claude/progress — never the read-only plugin cache) records
what the user has already been told about. Marker matches → silent, which
is every session except the first one after an install or upgrade.

The notice doubles as the discovery moment for the status-line integration:
if no renderer has ever polled the daemon (/health statusline_seen — the
accurate signal; nobody's settings are parsed), the hook asks Claude to
offer the setup. That covers the person who installed the plugin and never
found out the bars can live in their prompt.

Never blocks, never fails the session: every step degrades to silence."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _progress():
    spec = importlib.util.spec_from_file_location(
        "progress",
        Path(__file__).resolve().parent.parent / "scripts" / "progress.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    try:
        p = _progress()
        version = p.plugin_version()
        marker = p.home() / "last-version"
        seen = marker.read_text().strip() if marker.exists() else None
        if seen == version:
            return 0
        # Write first: a crash after this line costs one notice, while the
        # reverse ordering could nag every session forever.
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(version + "\n")

        health = p._get_json("/health", timeout=0.3) or {}
        wired = health.get("statusline_seen") is True

        if seen is None:
            lead = (f"[progress-channel] v{version} is newly installed. "
                    "At a natural moment (not mid-task), give the user a "
                    "one-line orientation: long-running work registers on "
                    "the channel and the page at http://127.0.0.1:7717/ "
                    "answers \"are we there yet\".")
        else:
            lead = (f"[progress-channel] upgraded {seen} -> {version}. "
                    "At a natural moment, mention it in one line; changes: "
                    "https://github.com/alexmond/alexmskills/blob/main/"
                    "CHANGELOG.md")
        if not wired:
            lead += (" Also: the status-line integration is NOT set up — the "
                     "session's live bars are not visible in the prompt. "
                     "Offer once to wire it (the SKILL.md 'Status line' "
                     "section has the exact settings.json edit; user can "
                     "just say \"set up the progress status line\").")

        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart", "additionalContext": lead}}))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
