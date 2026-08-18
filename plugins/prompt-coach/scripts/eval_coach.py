#!/usr/bin/env python3
"""prompt-coach eval harness — per-rule precision over a labeled golden set.

Issue #31's step 1. The coach's regex fast-filter is a harness component whose
false positives are harness defects; this measures them per rule instead of
discovering them one complaint at a time.

Two layers are deliberately separated:

  * This harness evaluates the FAST-FILTER: given prompt text in isolation,
    which rules should be candidates? That is mechanical and labelable.
  * The Claude-side veto (context resolves it) is NOT evaluated here — a
    candidate that context vetoes can still be a correct candidate. Rows may
    carry `fp_in_context: true` as an annotation, but it never affects scores.

Golden set: eval/golden.jsonl beside the plugin's scripts — one JSON object
per line:

  {"prompt": "...", "expect": ["rule-id", ...],   # [] means clean
   "confirmed": true,                              # human-verified label
   "era": "1.0.x" | "v0.10",                       # which analyzer produced it
   "source": "session|log|synthetic", "note": "..."}

Only confirmed rows score. Unconfirmed rows (e.g. from --import-logs) are
reported separately as draft coverage, never gated on — an auto-label copied
from the hook's own output would just measure the analyzer against itself.

Usage:
    eval_coach.py                        # score the golden set, report
    eval_coach.py --gate                 # exit 1 if any well-sampled rule dips
    eval_coach.py --import-logs [ROOT]   # harvest draft rows from repo logs
    eval_coach.py --json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLDEN = HERE.parent / "eval" / "golden.jsonl"
DRAFT = HERE.parent / "eval" / "draft.jsonl"

# The gate only judges rules with enough evidence to judge.
MIN_LABELED_FOR_GATE = 5
MIN_PRECISION = 0.80
MIN_RECALL = 0.60

_spec = importlib.util.spec_from_file_location("_pc_config", HERE / "config.py")
_cfg = importlib.util.module_from_spec(_spec)
sys.modules["_pc_config"] = _cfg
_spec.loader.exec_module(_cfg)


def load_rows(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            print(f"  ! {path.name}:{i} unparseable ({exc}) — skipped", file=sys.stderr)
    return rows


def evaluate(rows: list[dict]) -> dict:
    per: dict[str, dict] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    details = []
    for r in rows:
        fired, _pos = _cfg._analyze_one(r["prompt"])
        got = {ru.id for ru in fired}
        want = set(r.get("expect", []))
        for rid in got & want:
            per[rid]["tp"] += 1
        for rid in got - want:
            per[rid]["fp"] += 1
        for rid in want - got:
            per[rid]["fn"] += 1
        if got != want:
            details.append({"prompt": r["prompt"][:90], "expected": sorted(want),
                            "got": sorted(got), "note": r.get("note", "")})
    out = {}
    for rid, c in sorted(per.items()):
        n = c["tp"] + c["fp"] + c["fn"]
        prec = c["tp"] / (c["tp"] + c["fp"]) if (c["tp"] + c["fp"]) else None
        rec = c["tp"] / (c["tp"] + c["fn"]) if (c["tp"] + c["fn"]) else None
        out[rid] = {**c, "n": n, "precision": prec, "recall": rec}
    return {"rules": out, "mismatches": details, "rows": len(rows)}


def gate(report: dict) -> list[str]:
    fails = []
    for rid, s in report["rules"].items():
        if s["n"] < MIN_LABELED_FOR_GATE:
            continue
        if s["precision"] is not None and s["precision"] < MIN_PRECISION:
            fails.append(f"{rid}: precision {s['precision']:.2f} < {MIN_PRECISION} (n={s['n']})")
        if s["recall"] is not None and s["recall"] < MIN_RECALL:
            fails.append(f"{rid}: recall {s['recall']:.2f} < {MIN_RECALL} (n={s['n']})")
    return fails


LOG_LINE = re.compile(
    r"^- \[(\d{4}-\d{2}-\d{2})T[^\]]*\] fired=\[([^\]]*)\] chosen=\S* positives=\[[^\]]*\] "
    r"praise=\S* outcome=(\S+) prompt=«(.*)»\s*$")


def import_logs(root: Path) -> int:
    """Harvest DRAFT rows from every repo's coach log. The hook's own fires are
    weak labels (it only ran the active rules, and it is the thing under test),
    so everything lands unconfirmed — a human flips rows into golden.jsonl."""
    drafts, seen = [], set()
    existing = {r["prompt"] for r in load_rows(GOLDEN)} | {r["prompt"] for r in load_rows(DRAFT)}
    for log in sorted(root.glob("*/.claude/prompt-coach/log.md")):
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            m = LOG_LINE.match(line)
            if not m:
                continue
            date, fired_s, outcome, prompt = m.groups()
            if outcome.startswith("skipped:") or prompt in existing or prompt in seen:
                continue
            if len(prompt.split()) < 3 or prompt.startswith("<"):
                continue
            seen.add(prompt)
            fired = [] if fired_s.strip() in ("—", "") else [x.strip() for x in fired_s.split(",")]
            drafts.append({
                "prompt": prompt,
                "expect": fired,                     # DRAFT: the hook's own verdict
                "confirmed": False,
                "era": "1.0.x" if date >= "2026-08-08" else "v0.10",
                "source": f"log:{log.parent.parent.parent.name}",
                "note": f"auto from outcome={outcome}; verify before promoting",
            })
    DRAFT.parent.mkdir(parents=True, exist_ok=True)
    with DRAFT.open("a", encoding="utf-8") as fh:
        for d in drafts:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"  imported {len(drafts)} draft rows -> {DRAFT.relative_to(HERE.parent.parent.parent)}")
    print("  drafts are unconfirmed and never scored — promote verified rows into golden.jsonl")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--import-logs", nargs="?", const=str(Path.home() / "IdeaProjects"),
                    default=None, metavar="ROOT")
    args = ap.parse_args(argv)

    if args.import_logs:
        return import_logs(Path(args.import_logs).expanduser())

    rows = [r for r in load_rows(GOLDEN) if r.get("confirmed")]
    unconfirmed = len(load_rows(DRAFT)) + sum(1 for r in load_rows(GOLDEN) if not r.get("confirmed"))
    if not rows:
        print("  no confirmed golden rows yet — seed eval/golden.jsonl first", file=sys.stderr)
        return 2
    rep = evaluate(rows)

    if args.json:
        print(json.dumps(rep, indent=1))
    else:
        print(f"\n  prompt-coach eval — {rep['rows']} confirmed rows"
              f" ({unconfirmed} draft rows not scored)\n")
        print(f"  {'rule':<34} {'n':>3} {'prec':>6} {'rec':>6}")
        for rid, s in sorted(rep["rules"].items(), key=lambda kv: -(kv[1]['n'])):
            p = f"{s['precision']:.2f}" if s["precision"] is not None else "  —"
            r = f"{s['recall']:.2f}" if s["recall"] is not None else "  —"
            mark = "" if s["n"] >= MIN_LABELED_FOR_GATE else "  (below gate sample)"
            print(f"  {rid:<34} {s['n']:>3} {p:>6} {r:>6}{mark}")
        if rep["mismatches"]:
            print(f"\n  {len(rep['mismatches'])} mismatching rows:")
            for d in rep["mismatches"][:8]:
                print(f"    «{d['prompt']}»\n      expected={d['expected']} got={d['got']}")
    if args.gate:
        fails = gate(rep)
        if fails:
            print("\n  GATE FAILED:")
            for f in fails:
                print(f"    ✗ {f}")
            return 1
        print("\n  gate: every well-sampled rule within thresholds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
