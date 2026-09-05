#!/usr/bin/env python3
"""progress-channel MCP shim — the daemon's API as native tools.

A stdio MCP server (stdlib only, JSON-RPC over stdin/stdout) so Claude
sessions — and clients that cannot shell out — read and write the channel
as tools. It is deliberately a thin face on the daemon's existing HTTP API:
no state of its own, auto-spawns the daemon like any other producer.

Register (project .mcp.json or `claude mcp add`):
    {"mcpServers": {"progress": {"command": "python3",
                                 "args": ["<plugin>/scripts/progress_mcp.py"]}}}
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "progress", Path(__file__).resolve().parent / "progress.py")
progress = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(progress)

PROTOCOL = "2024-11-05"

TOOLS = [
    {
        "name": "progress_list",
        "description": "List every tracked long-running job (live and "
                       "recently finished) with state, counts, ETA, and "
                       "liveness verdicts (orphaned/stalled).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "progress_forecast",
        "description": "Pre-start duration forecast for a job name from its "
                       "run history — answers 'how long has this taken "
                       "before' prior to starting it.",
        "inputSchema": {"type": "object",
                        "properties": {"name": {"type": "string"}},
                        "required": ["name"]},
    },
    {
        "name": "progress_start",
        "description": "Register a new long-running job; returns a token for "
                       "progress_step/progress_finish.",
        "inputSchema": {"type": "object",
                        "properties": {"name": {"type": "string"},
                                       "total": {"type": "integer"},
                                       "detail": {"type": "string"}},
                        "required": ["name"]},
    },
    {
        "name": "progress_step",
        "description": "Advance a job started with progress_start.",
        "inputSchema": {"type": "object",
                        "properties": {"token": {"type": "string"},
                                       "n": {"type": "integer"},
                                       "done": {"type": "integer"},
                                       "detail": {"type": "string"}},
                        "required": ["token"]},
    },
    {
        "name": "progress_finish",
        "description": "Finish a job started with progress_start "
                       "(error makes it failed).",
        "inputSchema": {"type": "object",
                        "properties": {"token": {"type": "string"},
                                       "error": {"type": "string"}},
                        "required": ["token"]},
    },
]


def _text(payload) -> dict:
    body = payload if isinstance(payload, str) else json.dumps(payload, indent=1)
    return {"content": [{"type": "text", "text": body}]}


def call_tool(name: str, args: dict) -> dict:
    if name == "progress_list":
        progress.ensure_daemon()
        data = progress._get_json("/jobs?state=all")
        if not data:
            return _text("daemon unreachable — nothing tracked")
        return _text([progress._fmt_row(j) for j in data["jobs"]] or "(no jobs)")
    if name == "progress_forecast":
        progress.ensure_daemon()
        data = progress._get_json(
            "/forecast?name=" + progress.urllib.parse.quote(args["name"]))
        return _text(data["text"] if data else "daemon unreachable")
    if name == "progress_start":
        argv = ["--name", args["name"]]
        if args.get("total") is not None:
            argv += ["--total", str(args["total"])]
        if args.get("detail"):
            argv += ["--detail", args["detail"]]
        import contextlib, io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            progress.cmd_start(argv)
        return _text({"token": out.getvalue().strip()})
    if name == "progress_step":
        argv = [args["token"]]
        if args.get("done") is not None:
            argv += ["--done", str(args["done"])]
        elif args.get("n") is not None:
            argv += ["-n", str(args["n"])]
        if args.get("detail"):
            argv += ["--detail", args["detail"]]
        progress.cmd_step(argv)
        return _text("ok")
    if name == "progress_finish":
        argv = [args["token"]]
        if args.get("error"):
            argv += ["--fail", args["error"]]
        progress.cmd_finish(argv)
        return _text("ok")
    raise ValueError(f"unknown tool {name}")


def handle(req: dict) -> dict | None:
    method = req.get("method")
    if method == "initialize":
        result = {"protocolVersion": PROTOCOL,
                  "capabilities": {"tools": {}},
                  "serverInfo": {"name": "progress-channel", "version": "0.2.0"}}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        p = req.get("params", {})
        try:
            result = call_tool(p.get("name", ""), p.get("arguments") or {})
        except (SystemExit, Exception) as e:  # SystemExit: token errors
            result = {**_text(f"error: {e}"), "isError": True}
    elif method in ("notifications/initialized", "notifications/cancelled"):
        return None
    elif method == "ping":
        result = {}
    else:
        return {"jsonrpc": "2.0", "id": req.get("id"),
                "error": {"code": -32601, "message": f"unknown method {method}"}}
    if req.get("id") is None:  # a notification — never answer one
        return None
    return {"jsonrpc": "2.0", "id": req.get("id"), "result": result}


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
