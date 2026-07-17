#!/usr/bin/env python3
"""Generate the data-derived blocks of the Antora docs page.

Single source of truth: the SAME `build_dashboard()` data the web dashboard
renders. Three AsciiDoc blocks are generated so the docs can never drift from
the code:

  * generated-rules   — one labelled entry per rule, grouped by tier
                        (id / name / catches / bad->good example / reference URLs)
  * generated-summary — the catalog counts + tier sizes + positive/config totals
  * generated-config  — the full configuration-key reference, grouped by category
                        (key / type / default / description), from CONFIG_SCHEMA

Each block lives between a `// BEGIN generated-<name>` / `// END generated-<name>`
marker pair in `docs/modules/ROOT/pages/prompt-coach-beta.adoc`; --inject
replaces everything between each pair it finds (missing pairs are skipped with a
note). Re-run after any rule / count / config-schema change.

Usage:
    python3 gen-rules-doc.py                 # print all fragments to stdout
    python3 gen-rules-doc.py --inject        # rewrite the .adoc between markers
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]  # plugins/prompt-coach-beta/scripts -> repo root
ADOC = REPO / "docs/modules/ROOT/pages/prompt-coach-beta.adoc"
BEGIN = "// BEGIN generated-rules (gen-rules-doc.py — do not edit by hand)"
END = "// END generated-rules"
SUM_BEGIN = "// BEGIN generated-summary (gen-rules-doc.py — do not edit by hand)"
SUM_END = "// END generated-summary"
CFG_BEGIN = "// BEGIN generated-config (gen-rules-doc.py — do not edit by hand)"
CFG_END = "// END generated-config"

TIER_LABEL = {
    1: "L1 — fundamentals",
    2: "L2 — intermediate",
    3: "L3 — classical prompting techniques",
    4: "L4 — goals & loops",
    5: "L5 — Claude-Code tool-native",
    6: "L6 — skill-awareness",
}
CONFIG_CATEGORY_ORDER = [
    "output", "rule-activation", "mastery", "praise", "typo-tolerance",
    "llm-fallback",
]


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


def render_summary(data: dict) -> str:
    """One-paragraph catalog summary: total rules, per-tier sizes, positive
    detector count, and configuration-key count — all counted from the data."""
    rules = data["rules"]
    n = len(rules)
    sizes = {t: sum(1 for r in rules if r["tier"] == t) for t in sorted(TIER_LABEL)}
    per_tier = " · ".join(f"L{t} {sizes[t]}" for t in sorted(sizes) if sizes[t])
    n_cfg = len(data.get("config", []))
    return (
        f"{SUM_BEGIN}\n\n"
        f"The catalog ships **{n} rules** across {len(TIER_LABEL)} tiers "
        f"({per_tier}), each with a mirroring **positive detector** ({n} total) "
        f"so mastery is *earned by demonstration*. Behavior is tuned by "
        f"**{n_cfg} configuration keys** (see <<config-reference>>).\n\n"
        f"{SUM_END}\n"
    )


def _fmt_default(v) -> str:
    if isinstance(v, bool):
        return "`true`" if v else "`false`"
    if v is None:
        return "—"
    if isinstance(v, (dict, list)):
        return f"`{_cell(json.dumps(v, separators=(',', ':')))}`"
    return f"`{_cell(str(v))}`"


def _cell(text: str) -> str:
    """Make a value safe for an AsciiDoc table cell: no pipes, no newlines."""
    return " ".join(str(text).replace("|", "\\|").split())


def render_config(data: dict) -> str:
    """Full configuration-key reference table grouped by category, from the
    same CONFIG_SCHEMA the validator uses. Key / type / default / description."""
    keys = data.get("config", [])
    by_cat: dict[str, list[dict]] = {}
    for k in keys:
        by_cat.setdefault(k.get("category", "other"), []).append(k)
    ordered = [c for c in CONFIG_CATEGORY_ORDER if c in by_cat]
    ordered += sorted(c for c in by_cat if c not in CONFIG_CATEGORY_ORDER)
    lines: list[str] = [CFG_BEGIN, ""]
    for cat in ordered:
        lines.append(f".`{cat}`")
        lines.append('[cols="2,1,1,4",options="header"]')
        lines.append("|===")
        lines.append("| Key | Type | Default | What it does")
        for k in sorted(by_cat[cat], key=lambda x: x["key"]):
            desc = _cell(k.get("description", ""))
            lines.append(
                f"| `{k['key']}` | {k.get('type', 'str')} "
                f"| {_fmt_default(k.get('default'))} | {desc}")
        lines.append("|===")
        lines.append("")
    lines.append(CFG_END)
    return "\n".join(lines) + "\n"


def _inject_block(text: str, begin: str, end: str, fragment: str) -> tuple[str, bool]:
    """Replace the region between begin/end with fragment. Returns (text, done).
    done is False (with a note) when the markers aren't present."""
    if begin not in text or end not in text:
        print(f"note: markers not found for {begin.split('(')[0].strip()} — skipped")
        return text, False
    pre = text.split(begin)[0].rstrip("\n")
    post = text.split(end, 1)[1].lstrip("\n")
    return pre + "\n\n" + fragment.rstrip("\n") + "\n\n" + post, True


def inject(data: dict) -> None:
    text = ADOC.read_text()
    text, r_ok = _inject_block(text, BEGIN, END, render(data))
    text, s_ok = _inject_block(text, SUM_BEGIN, SUM_END, render_summary(data))
    text, c_ok = _inject_block(text, CFG_BEGIN, CFG_END, render_config(data))
    ADOC.write_text(text)
    print(f"injected into {ADOC}: rules={r_ok} summary={s_ok} config={c_ok} "
          f"({len(data['rules'])} rules, {len(data.get('config', []))} config keys)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--inject", action="store_true",
                    help="rewrite the .adoc between the generated-* markers")
    args = ap.parse_args()
    cfg = _load_config()
    data = cfg.build_dashboard(Path("/tmp"))
    if args.inject:
        inject(data)
    else:
        sys.stdout.write(render(data))
        sys.stdout.write("\n")
        sys.stdout.write(render_summary(data))
        sys.stdout.write("\n")
        sys.stdout.write(render_config(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
