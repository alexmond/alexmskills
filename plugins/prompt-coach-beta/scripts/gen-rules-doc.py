#!/usr/bin/env python3
"""Generate the per-rule reference block for the Antora docs page.

Single source of truth: the SAME `build_dashboard()` data the web dashboard
renders (id / tier / name / catches / example / reference URLs). Emits an
AsciiDoc fragment — one labelled entry per rule, grouped by tier — that
replaces the terse "What it watches for" tables in
`docs/modules/ROOT/pages/prompt-coach-beta.adoc`, so the docs and the
dashboard never drift.

Usage:
    python3 gen-rules-doc.py                 # print the fragment to stdout
    python3 gen-rules-doc.py --inject        # rewrite the .adoc between markers

The .adoc carries a `// BEGIN generated-rules` / `// END generated-rules`
marker pair; --inject replaces everything between them. Re-run after any rule
add / rename / help-text or source-link change.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]  # plugins/prompt-coach-beta/scripts -> repo root
ADOC = REPO / "docs/modules/ROOT/pages/prompt-coach-beta.adoc"
BEGIN = "// BEGIN generated-rules (gen-rules-doc.py — do not edit by hand)"
END = "// END generated-rules"

TIER_LABEL = {
    1: "L1 — fundamentals",
    2: "L2 — intermediate",
    3: "L3 — classical prompting techniques",
    4: "L4 — goals & loops",
    5: "L5 — Claude-Code tool-native",
    6: "L6 — skill-awareness",
}


def _load_config():
    spec = importlib.util.spec_from_file_location("_pc_config", HERE / "config.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pretty_ref(ref: str) -> str:
    """`be-clear-and-direct` -> `Be clear and direct` for a link label."""
    return ref.replace("-", " ").capitalize()


def _refs(rule: dict) -> list[tuple[str, str]]:
    """Deduped (title, url) reference list: the exact Anthropic-guide anchor
    first (if any), then every cited source, skipping URL duplicates."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    anth = rule.get("anthropic_url")
    if anth:
        out.append((f"Anthropic guide: {_pretty_ref(rule['anthropic_ref'])}", anth))
        seen.add(anth)
    for s in rule.get("sources", []):
        u = s.get("url")
        if u and u not in seen:
            out.append((s.get("title", u), u))
            seen.add(u)
    return out


def _esc(text: str) -> str:
    """Keep example strings from tripping AsciiDoc inline markup. They render
    inside a single-line backtick monospace span, so a literal backtick and an
    embedded newline are the real hazards; collapse both."""
    return " ".join(text.replace("`", "‘").split())


def render(data: dict) -> str:
    rules = sorted(data["rules"], key=lambda r: (r["tier"], r["id"]))
    lines: list[str] = [BEGIN, ""]
    for tier in sorted(TIER_LABEL):
        group = [r for r in rules if r["tier"] == tier]
        if not group:
            continue
        lines.append(f"=== {TIER_LABEL[tier]}")
        lines.append("")
        for r in group:
            catches = r.get("catches") or r.get("guidance", "")
            bad = _esc(r.get("example_bad", "").strip())
            good = _esc(r.get("example_good", "").strip())
            lines.append(f"`{r['id']}` — *{r['name']}*::")
            lines.append(catches.strip())
            if bad and good:
                lines.append("+")
                lines.append(f"✗ `{bad}` +")
                lines.append(f"✓ `{good}`")
            refs = _refs(r)
            if refs:
                lines.append("+")
                links = " · ".join(f"{u}[{t}^]" for t, u in refs)
                lines.append(f"_Refs:_ {links}")
            lines.append("")
    lines.append(END)
    return "\n".join(lines) + "\n"


def inject(fragment: str) -> None:
    text = ADOC.read_text()
    if BEGIN not in text or END not in text:
        sys.exit(
            f"markers not found in {ADOC} — add\n  {BEGIN}\n  {END}\n"
            "around the block to replace, then re-run --inject."
        )
    pre = text.split(BEGIN)[0].rstrip("\n")
    post = text.split(END, 1)[1].lstrip("\n")
    ADOC.write_text(pre + "\n\n" + fragment + "\n" + post)
    print(f"injected {fragment.count('::')} rules into {ADOC}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--inject", action="store_true",
                    help="rewrite the .adoc between the generated-rules markers")
    args = ap.parse_args()
    cfg = _load_config()
    data = cfg.build_dashboard(Path("/tmp"))
    fragment = render(data)
    if args.inject:
        inject(fragment)
    else:
        sys.stdout.write(fragment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
