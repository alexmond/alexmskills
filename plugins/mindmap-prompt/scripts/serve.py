#!/usr/bin/env python3
"""Local canvas server for mindmap-prompt.

Serves page/mindmap.html and a tiny JSON API on 127.0.0.1. Stdlib only, no
dependencies, and it never talks to the network — the page calls back here, and
here calls `mindmap.py`, so the compiler stays the single source of truth
instead of being reimplemented in JavaScript.

    serve.py [--port 8770] [--cwd <repo>] [--no-open]

Maps live in <repo>/.claude/mindmap/*.canvas — in the *consuming* repo, never
in the plugin directory, which is a read-only cache when installed.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import threading
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
PAGE = HERE.parent / "page" / "mindmap.html"
MAX_BODY = 4 * 1024 * 1024          # a mind map is text; 4 MB is already absurd
SAFE_NAME = re.compile(r"^[\w][\w.-]{0,63}$")

_spec = importlib.util.spec_from_file_location("_mm", HERE / "mindmap.py")
mindmap = importlib.util.module_from_spec(_spec)
sys.modules["_mm"] = mindmap
_spec.loader.exec_module(mindmap)


def maps_dir(root: Path) -> Path:
    d = root / ".claude" / "mindmap"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe(name: str) -> str:
    """Reject anything that isn't a plain file name. The server is loopback-only,
    but a stray `../` would still write outside the repo."""
    name = (name or "").strip()
    if name.endswith(".canvas"):
        name = name[: -len(".canvas")]
    if not SAFE_NAME.match(name):
        raise ValueError(f"bad map name: {name!r}")
    return name


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    root: Path = Path.cwd()

    # -------------------------------------------------- helpers
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8")

    def _err(self, code: int, msg: str) -> None:
        self._send(code, msg.encode("utf-8"), "text/plain; charset=utf-8")

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("request too large")
        return json.loads(self.rfile.read(n) or b"{}")

    def log_message(self, *a):        # keep the terminal for the user's own output
        pass

    # -------------------------------------------------- routes
    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            try:
                return self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            except OSError as exc:
                return self._err(500, f"cannot read the page: {exc}")

        if u.path == "/api/maps":
            names = sorted(p.name for p in maps_dir(self.root).glob("*.canvas"))
            return self._json({"maps": names})

        if u.path == "/api/map":
            q = parse_qs(u.query).get("name", [""])[0]
            try:
                path = maps_dir(self.root) / (_safe(q) + ".canvas")
                return self._json({"name": path.name, "canvas": json.loads(path.read_text("utf-8"))})
            except ValueError as exc:
                return self._err(400, str(exc))
            except OSError:
                return self._err(404, "no such map")
            except json.JSONDecodeError as exc:
                return self._err(422, f"map is not valid JSON: {exc}")

        return self._err(404, "not found")

    def do_POST(self):
        u = urlparse(self.path)
        try:
            data = self._body()
        except (ValueError, json.JSONDecodeError) as exc:
            return self._err(400, f"bad request body: {exc}")

        if u.path == "/api/map":
            try:
                name = _safe(data.get("name", ""))
            except ValueError as exc:
                return self._err(400, str(exc))
            canvas = data.get("canvas")
            if not isinstance(canvas, dict):
                return self._err(400, "missing 'canvas' object")
            path = maps_dir(self.root) / f"{name}.canvas"
            path.write_text(json.dumps(canvas, indent=2) + "\n", encoding="utf-8")
            return self._json({"path": str(path.relative_to(self.root))})

        if u.path == "/api/compile":
            canvas = data.get("canvas")
            if not isinstance(canvas, dict):
                return self._err(400, "missing 'canvas' object")
            mm = mindmap.MindMap(canvas)
            report = mindmap.validate(mm)
            errors = [r for r in report if r[0] == "error"]
            out = {"ok": not errors, "report": [list(r) for r in report], "markdown": ""}
            if not errors and not data.get("validateOnly"):
                out["markdown"] = mindmap.compile_prompt(
                    mm, include_orphans=bool(data.get("includeOrphans"))
                )
            return self._json(out)

        return self._err(404, "not found")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--cwd", default=".", help="repo whose .claude/mindmap/ holds the maps")
    ap.add_argument("--map", help="open this map on start")
    ap.add_argument("--no-open", action="store_true", help="don't launch a browser")
    args = ap.parse_args(argv)

    Handler.root = Path(args.cwd).resolve()
    maps_dir(Handler.root)

    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as exc:
        print(f"cannot bind 127.0.0.1:{args.port} — {exc}", file=sys.stderr)
        return 1

    url = f"http://127.0.0.1:{args.port}/"
    if args.map:
        url += f"?map={args.map}"
    print(f"  mindmap-prompt → {url}")
    print(f"  maps: {maps_dir(Handler.root)}")
    print("  Ctrl-C to stop")
    if not args.no_open:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
