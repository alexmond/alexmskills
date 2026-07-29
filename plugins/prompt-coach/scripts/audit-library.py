#!/usr/bin/env python3
"""Calibration audit: run the full rule catalog over Anthropic's gold-standard
Prompt Library and report where the coach over-fires.

The library prompts (see gen-prompt-library.py) are examples Anthropic ships as
*good* Claude Code prompts. This runs every one through the analyzer and reports
the clean rate + which rules fire on gold prompts. It is a REPORT, not a gate:
many library prompts are terse templates (slots for the user to fill), so some
firings are legitimate ("migrate everything…" really does lack a guardrail) —
the value is spotting the *false* positives (a rule firing on a genuinely
well-formed prompt) so they can be tuned.

    python3 audit-library.py            # human report
    python3 audit-library.py --json     # machine-readable
    python3 audit-library.py --show-fires vague-reference   # list what a rule fired on
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name: str, fname: str):
    spec = importlib.util.spec_from_file_location(name, HERE / fname)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def run() -> dict:
    cfg = _load("_pc_config_audit", "config.py")
    lib = _load("_pc_library_audit", "library.py")
    entries = lib.load().get("entries", [])
    rows = []
    fire_counts: dict[str, int] = {}
    clean = 0
    for e in entries:
        text = lib.fill(e)
        fired, _ = cfg._analyze_one(text)
        ids = [r.id for r in fired]
        if not ids:
            clean += 1
        for rid in ids:
            fire_counts[rid] = fire_counts.get(rid, 0) + 1
        rows.append({"id": e.get("id"), "cat": e.get("cat"), "prompt": text,
                     "fired": ids})
    total = len(entries) or 1
    return {
        "total": len(entries),
        "clean": clean,
        "clean_pct": round(100 * clean / total),
        "fire_counts": dict(sorted(fire_counts.items(), key=lambda x: -x[1])),
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--show-fires", metavar="RULE_ID",
                    help="list the gold prompts a given rule fired on")
    args = ap.parse_args()
    data = run()

    if args.show_fires:
        hits = [r for r in data["rows"] if args.show_fires in r["fired"]]
        if args.json:
            print(json.dumps(hits, indent=2, ensure_ascii=False))
        else:
            print(f"{args.show_fires} fired on {len(hits)} gold prompt(s):")
            for r in hits:
                print(f"  ({r['cat']}) «{r['prompt'][:80]}»")
        return 0

    if args.json:
        print(json.dumps({k: v for k, v in data.items() if k != "rows"}, indent=2))
        return 0

    print(f"Prompt-Library calibration audit — {data['total']} gold prompts")
    print(f"  clean (0 rules fired): {data['clean']}/{data['total']} "
          f"= {data['clean_pct']}%")
    print("\n  rules firing on gold prompts (false-positive candidates):")
    for rid, n in data["fire_counts"].items():
        print(f"    {n:2d}  {rid}")
    print("\n  Note: a report, not a gate. Terse templates legitimately trip "
          "guardrail/verify rules;\n  inspect a rule's hits with "
          "`--show-fires <rule-id>` to separate real fires from FPs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
