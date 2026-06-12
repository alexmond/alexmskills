#!/usr/bin/env python3
"""PreToolUse phase-gate hook for dev-crew.

Machine-enforces the relay's handoff contract at phase boundaries — prompt
discipline drifts, hooks don't:

  - dc-dev may not start without CONTRACT.md in the current run dir
  - dc-qa may not start without CHANGES.md
  - dc-deployer may not start without QA.md, and QA.md must not contain a
    FAIL verdict
  - any required handoff carrying `status: BLOCKED` stops the advance and
    routes the conductor to the escalation ladder instead

Reads the Task tool input on stdin; keys off the dc-<role> the conductor is
delegating to. The "current run" is the newest directory under
.claude/dev-crew/runs/. Defensive by design: on any uncertainty (no run dir,
unparseable input, non-crew Task) it stays silent and allows. Exits 0 always.
"""
from __future__ import annotations

import glob
import json
import os
import sys

RUNS_GLOB = os.path.join(".claude", "dev-crew", "runs", "*")

# role being delegated to -> handoff file that must already exist
REQUIRES = {
    "dc-dev": "CONTRACT.md",
    "dc-qa": "CHANGES.md",
    "dc-deployer": "QA.md",
}


def deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    inp = payload.get("tool_input") or {}
    text = " ".join(
        str(inp.get(k, "")) for k in ("subagent_type", "description", "prompt")
    )

    role = next((r for r in REQUIRES if r in text), None)
    if role is None:
        return 0

    runs = sorted(glob.glob(RUNS_GLOB), key=os.path.getmtime, reverse=True)
    run_dir = next((d for d in runs if os.path.isdir(d)), None)
    if run_dir is None:
        return 0  # no relay in progress — not ours to gate

    required = os.path.join(run_dir, REQUIRES[role])
    if not os.path.isfile(required):
        deny(
            f"dev-crew phase gate: {role} requires {REQUIRES[role]} in {run_dir} and it "
            f"doesn't exist. The previous role hasn't handed off — capture its output to "
            f"the file (handoff discipline) or re-run that role before advancing."
        )
        return 0

    try:
        content = open(required, encoding="utf-8").read()
    except OSError:
        return 0

    if "status: BLOCKED" in content:
        deny(
            f"dev-crew phase gate: {REQUIRES[role]} reports status: BLOCKED. Don't advance "
            f"to {role} — run the escalation ladder (clarify/retry → re-tier vs re-role by "
            f"diagnosis → re-plan → user). See the BLOCKED block in {required}."
        )
        return 0

    if role == "dc-deployer" and "FAIL" in content:
        deny(
            f"dev-crew phase gate: QA.md contains a FAIL verdict — the QA gate blocks the "
            f"deployer. Route back to dev with QA.md as the defect list (max two loops), "
            f"or escalate. File: {required}"
        )
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
