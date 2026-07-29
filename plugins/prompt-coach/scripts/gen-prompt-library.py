#!/usr/bin/env python3
"""Refresh the local snapshot of Anthropic's Claude Code Prompt Library.

The library is a set of tagged, slot-templated example prompts published at
https://code.claude.com/docs/en/prompt-library — embedded in the page as a
`const RAW = useMemo(() => [ … ])` array. This script fetches the page (stdlib
urllib only), extracts and parses that array, and writes a stable JSON snapshot
to `data/prompt-library.json` that the coach reads offline (never fetched at
hook time). Mirrors gen-rules-doc.py: a deliberate, re-runnable refresh.

    python3 gen-prompt-library.py             # fetch live → data/prompt-library.json
    python3 gen-prompt-library.py --from-file page.html   # parse a saved page
    python3 gen-prompt-library.py --check     # parse only, print counts, no write

Provenance: the prompts are Anthropic documentation content (not this plugin's
work). The snapshot records source_url + a note; it is vendored for offline
matching, with attribution, and refreshed deliberately — not claimed as ours.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data" / "prompt-library.json"
SOURCE_URL = "https://code.claude.com/docs/en/prompt-library"
NOTE = ("Anthropic Claude Code Prompt Library — documentation content, vendored "
        "as an offline snapshot for local task-matching, with attribution. Not "
        "original to this plugin. Refresh with scripts/gen-prompt-library.py.")


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 (fixed URL)
        return r.read().decode("utf-8", "replace")


def _unescape(s: str) -> str:
    # JS single-quoted string body → plain text (handle \' \\ \n).
    return s.replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\").replace("\\n", "\n")


def parse_library(page: str) -> list[dict]:
    """Extract the RAW entry array. The schema is flat and known, so parse each
    entry with field-scoped regexes (robust to key order / missing keys)."""
    # The array is embedded inside a Next.js RSC payload, so `>` `<` `&` arrive
    # unicode-escaped (`=>`). Decode `\uXXXX` first so the literals match.
    page = re.sub(r"\\u([0-9a-fA-F]{4})", lambda mm: chr(int(mm.group(1), 16)), page)
    m = re.search(r"const RAW\s*=\s*useMemo\(\(\)\s*=>\s*\[", page)
    if not m:
        raise SystemExit("could not locate `const RAW = useMemo(() => [` in page")
    body = page[m.end():]
    # entries are `{ id: '…', … }` — split on the id key, which every entry has.
    chunks = re.split(r"\bid:\s*'", body)[1:]
    entries: list[dict] = []
    for c in chunks:
        idm = re.match(r"((?:[^'\\]|\\.)*)'", c)
        if not idm:
            continue
        e: dict = {"id": _unescape(idm.group(1))}

        def field(key: str):
            fm = re.search(rf"{key}:\s*'((?:[^'\\]|\\.)*)'", c)
            return _unescape(fm.group(1)) if fm else None

        for k in ("sdlc", "cat", "src", "nextHref"):
            v = field(k)
            if v is not None:
                e[k] = v
        pm = re.search(r"prompt:\s*'((?:[^'\\]|\\.)*)'", c)
        if pm:
            e["prompt"] = _unescape(pm.group(1))
        rm = re.search(r"roles:\s*\[([^\]]*)\]", c)
        e["roles"] = re.findall(r"'([^']+)'", rm.group(1)) if rm else []
        sm = re.search(r"slots:\s*\{([^{}]*)\}", c, re.S)
        if sm:
            e["slots"] = {k: _unescape(v) for k, v in
                          re.findall(r"(\w+):\s*'((?:[^'\\]|\\.)*)'", sm.group(1))}
        nm = re.search(r"startN:\s*(\d+)", c)
        if nm:
            e["startN"] = int(nm.group(1))
        if e.get("prompt"):
            entries.append(e)
    if len(entries) < 10:
        raise SystemExit(f"parsed only {len(entries)} entries — page format may have changed")
    return entries


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from-file", help="parse a saved page instead of fetching")
    ap.add_argument("--check", action="store_true", help="parse + report, do not write")
    args = ap.parse_args()

    page = Path(args.from_file).read_text() if args.from_file else _fetch(SOURCE_URL)
    entries = parse_library(page)

    phases = sorted({e.get("sdlc", "?") for e in entries})
    cats = sorted({e.get("cat", "?") for e in entries})
    print(f"parsed {len(entries)} entries · phases={phases} · {len(cats)} categories")
    if args.check:
        return 0

    DATA.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_url": SOURCE_URL,
        "note": NOTE,
        "count": len(entries),
        "entries": entries,
    }
    DATA.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {DATA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
