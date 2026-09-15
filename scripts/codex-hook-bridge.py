#!/usr/bin/env python3
"""Vendored Codex envelope adapter; Claude handlers remain the source of rules.

Copied by gen-codex-manifests.py into opted-in plugins. Never writes source
files. Patch updates pass only added/removed lines to existing Edit checks.
"""
from __future__ import annotations
import json
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys


def envelopes(payload):
    inp = payload.get("tool_input") or {}
    name = payload.get("tool_name", "")
    if not isinstance(inp, (str, dict)):
        return
    patch = inp if isinstance(inp, str) else inp.get("input", inp.get("patch", inp.get("command", "")))
    if isinstance(patch, str) and patch.startswith("*** Begin Patch"):
        current = None
        for line in patch.splitlines():
            if line.startswith(("*** Add File: ", "*** Update File: ", "*** Delete File: ", "*** End Patch")):
                if current:
                    yield current
                current = None
                if line.startswith(("*** Add File: ", "*** Update File: ")):
                    add = line.startswith("*** Add File:")
                    current = dict(payload, tool_name="Write" if add else "Edit", tool_input={
                        "file_path": line.split(": ", 1)[1],
                        **({"content": ""} if add else {"new_string": "", "old_string": ""})})
            elif current and line.startswith("*** Move to: "):
                current["tool_input"]["file_path"] = line.split(": ", 1)[1]
            elif current and line.startswith("+"):
                key = "content" if current["tool_name"] == "Write" else "new_string"
                current["tool_input"][key] += line[1:] + "\n"
            elif current and current["tool_name"] == "Edit" and line.startswith("-"):
                current["tool_input"]["old_string"] += line[1:] + "\n"
        if current:
            yield current
        return
    if not isinstance(inp, dict):
        return
    if name in {"exec_command", "shell_command", "Bash"}:
        payload = dict(payload, tool_name="Bash", tool_input=dict(inp, command=inp.get("command", inp.get("cmd", ""))))
    yield payload


def relevant(item, handler):
    """Avoid interpreter startup for unrelated files in large multi-file patches."""
    if item.get("tool_name") not in {"Write", "Edit"}:
        return True
    inp = item.get("tool_input") or {}
    path = inp.get("file_path") or inp.get("filePath") or ""
    if handler.endswith("lint-claude-md.py"):
        return Path(path).name in {"CLAUDE.md", "AGENTS.md", "AGENTS.override.md"}
    if handler.endswith("lint-memory-write.py"):
        parts = Path(path).parts
        return any(parts[i:i+2] == (".codex", "memory") for i in range(len(parts)-2)) or ".claude" in parts
    return True


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
        if payload.get("cwd"):
            os.chdir(payload["cwd"])
    except (ValueError, OSError):
        return 0
    os.environ["SKILL_CLIENT"] = "codex"
    instructions = next((n for n in ("AGENTS.override.md", "AGENTS.md", "CLAUDE.md") if Path(n).is_file()), "AGENTS.md")
    os.environ["SKILL_INSTRUCTIONS_FILE"] = instructions
    event = payload.get("hook_event_name", "SessionStart")
    if sys.argv[1] == "--memory":
        index = Path(".codex/memory/MEMORY.md")
        if index.is_file():
            context = "Project memory index (.codex/memory/; read relevant linked files as needed):\n" + index.read_text()[:16000]
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}))
        return 0
    root = Path(__file__).resolve().parent.parent
    contexts, reasons, common = [], [], {}
    lint = None
    for item in envelopes(payload):
        if not relevant(item, sys.argv[1]):
            continue
        if Path(sys.argv[1]).name in {"lint-claude-md.py", "lint-memory-write.py"}:
            # These two pure stdin/stdout handlers share one interpreter for the
            # whole patch, including patches with many instruction/memory files.
            if lint is None:
                spec = importlib.util.spec_from_file_location("_codex_lint", root / sys.argv[1])
                lint = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(lint)
            output = io.StringIO()
            stdin = sys.stdin
            try:
                sys.stdin = io.StringIO(json.dumps(item))
                with contextlib.redirect_stdout(output):
                    lint.main()
            finally:
                sys.stdin = stdin
            stdout = output.getvalue()
        else:
            proc = subprocess.run([sys.executable, str(root / sys.argv[1]), *sys.argv[2:]],
                                  input=json.dumps(item), text=True, capture_output=True, timeout=8)
            stdout = proc.stdout
        if not stdout.strip():
            continue
        try:
            result = json.loads(stdout)
        except ValueError:
            continue
        # Audit prose names the selected instructions, while Claude output is untouched.
        result = json.loads(json.dumps(result).replace("CLAUDE.md", instructions))
        specific = result.get("hookSpecificOutput", {})
        if specific.get("permissionDecision") == "deny":
            reasons.append(specific.get("permissionDecisionReason", "Plugin check failed"))
            break  # One failing file rejects the entire patch; do not risk hook timeout.
        if specific.get("additionalContext"):
            contexts.append(specific["additionalContext"])
        for key in ("decision", "reason", "systemMessage", "continue", "stopReason"):
            if key in result:
                common[key] = result[key]
    if reasons:
        common["hookSpecificOutput"] = {"hookEventName": event, "permissionDecision": "deny", "permissionDecisionReason": "\n".join(reasons)}
    elif contexts:
        if event == "PostCompact":
            common["systemMessage"] = "\n".join(contexts)
        else:
            common["hookSpecificOutput"] = {"hookEventName": event, "additionalContext": "\n".join(contexts)}
    # Advisory handlers must not turn a suggestion into an approval override.
    if common:
        print(json.dumps(common))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
