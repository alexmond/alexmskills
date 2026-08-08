#!/usr/bin/env python3
"""mindmap-prompt release gate — run with `make test-mindmap`.

The compiler is the source of truth for map -> prompt, so it gets a real gate
before any UI exists: a golden fixture, the graph invariants that are easy to
regress, and the validation rules.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent / "tests" / "fixtures"

_spec = importlib.util.spec_from_file_location("_mm", HERE / "mindmap.py")
mm_mod = importlib.util.module_from_spec(_spec)
sys.modules["_mm"] = mm_mod
_spec.loader.exec_module(mm_mod)

_sspec = importlib.util.spec_from_file_location("_srv", HERE / "serve.py")
srv_mod = importlib.util.module_from_spec(_sspec)
sys.modules["_srv"] = srv_mod
_sspec.loader.exec_module(srv_mod)

_failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✓' if ok else '✗'} {name}")
    if not ok:
        _failures.append(f"{name}{(' — ' + detail) if detail else ''}")
        if detail:
            print(f"      {detail}")


def _map(nodes, edges=()):
    return mm_mod.MindMap({"nodes": nodes, "edges": list(edges)})


def _node(nid, text, x=0, y=0, ntype="text"):
    return {"id": nid, "type": ntype, "x": x, "y": y, "width": 100, "height": 50, "text": text}


def _levels(report):
    return [lvl for lvl, _ in report]


# --------------------------------------------------------------------------


def t_golden_fixture():
    """The reference map compiles byte-for-byte to the committed prompt."""
    mm = mm_mod.load(FIXTURES / "dark-mode.canvas")
    got = mm_mod.compile_prompt(mm)
    want = (FIXTURES / "dark-mode.expected.md").read_text(encoding="utf-8")
    if got != want:
        import difflib
        diff = "\n".join(list(difflib.unified_diff(
            want.splitlines(), got.splitlines(), "expected", "got", lineterm=""))[:14])
        check("golden fixture compiles to the expected prompt", False, diff)
    else:
        check("golden fixture compiles to the expected prompt", True)


def t_bfs_ownership():
    """A node wired straight to the goal stays top-level even when a longer
    branch also reaches it. Plain DFS buried it — this is that regression."""
    mm = mm_mod.load(FIXTURES / "dark-mode.canvas")
    out = mm_mod.compile_prompt(mm)
    palette_top = "\n## Color palette\n" in out
    not_buried = "### Color palette" not in out and "#### Color palette" not in out
    referenced_once = out.count('→ see "Color palette"') == 1
    single_section = out.count("Color palette") == 2  # heading + the reference
    check("BFS spanning tree keeps a direct child top-level, cross-link is a reference",
          palette_top and not_buried and referenced_once and single_section,
          f"top={palette_top} not_buried={not_buried} ref={referenced_once} count_ok={single_section}")


def t_no_duplication_and_cycles_terminate():
    """A cycle must not hang or repeat content."""
    nodes = [_node("g", "#goal Loop it\n\nDone = it terminates."),
             _node("a", "#feature A", y=100), _node("b", "#feature B", y=200)]
    edges = [{"fromNode": "g", "toNode": "a"}, {"fromNode": "a", "toNode": "b"},
             {"fromNode": "b", "toNode": "a"}]
    mm = _map(nodes, edges)
    out = mm_mod.compile_prompt(mm)
    check("cycles terminate, node rendered once + referenced",
          out.count("## A") == 1 and out.count('→ see "A"') == 1 and mm.has_cycle(),
          out.replace("\n", "⏎"))


def t_reading_order():
    """Sibling order follows canvas layout (y then x), not JSON order."""
    nodes = [_node("g", "#goal Order\n\nDone = sorted."),
             _node("late", "#feature Bottom", x=0, y=900),
             _node("early", "#feature Top", x=0, y=100),
             _node("mid", "#feature Middle right", x=500, y=100)]
    edges = [{"fromNode": "g", "toNode": n} for n in ("late", "early", "mid")]
    out = mm_mod.compile_prompt(_map(nodes, edges))
    order = [out.index(t) for t in ("## Top", "## Middle right", "## Bottom")]
    check("siblings compile in canvas reading order (y, then x)", order == sorted(order), str(order))


def t_kinds_and_default():
    """Kind tags parse; an untagged node is an idea; tags are case-insensitive."""
    cases = [
        ("#goal Ship it", "goal", "Ship it"),
        ("#CONSTRAINT Do not touch auth", "constraint", "Do not touch auth"),
        ("#feature Toggle\n\nbody", "feature", "Toggle"),
        ("just an idea", "idea", "just an idea"),
        ("#unknown-tag thing", "idea", "#unknown-tag thing"),
    ]
    bad = [c for c in cases if mm_mod.parse_node_text(c[0])[:2] != (c[1], c[2])]
    check("kind tags parse (case-insensitive), untagged defaults to idea",
          not bad, f"mismatched: {bad}")


def t_constraints_sectioned():
    """Constraints compile into their own section, never inline in the body."""
    nodes = [_node("g", "#goal Do a thing\n\nDone = done."),
             _node("f", "#feature Feature", y=100),
             _node("c", "#constraint Never touch the schema", y=200)]
    edges = [{"fromNode": "g", "toNode": "f"}, {"fromNode": "g", "toNode": "c"}]
    out = mm_mod.compile_prompt(_map(nodes, edges))
    check("constraints go to their own section, not the body tree",
          "## Constraints" in out
          and "- Never touch the schema" in out
          and "## Never touch the schema" not in out, out.replace("\n", "⏎"))


def t_validation_errors():
    """Errors: no goal, two goals, empty node, goal with no edges."""
    no_goal = mm_mod.validate(_map([_node("a", "#idea lonely")]))
    two = mm_mod.validate(_map([_node("g1", "#goal One"), _node("g2", "#goal Two", y=99)]))
    empty = mm_mod.validate(_map([_node("g", "#goal Fine\n\nDone = x."), _node("e", "   ", y=50)],
                                 [{"fromNode": "g", "toNode": "e"}]))
    stranded = mm_mod.validate(_map([_node("g", "#goal Alone\n\nDone = x.")]))
    check("validation flags: missing goal / duplicate goal / empty node / goal with no edges",
          "error" in _levels(no_goal) and "error" in _levels(two)
          and "error" in _levels(empty) and "error" in _levels(stranded))


def t_validation_warns_orphans_and_done():
    """Orphans and a goal with no done-criteria warn but never block."""
    mm = mm_mod.load(FIXTURES / "dark-mode.canvas")
    rep = mm_mod.validate(mm)
    orphan_warn = any(lvl == "warn" and "not connected" in msg for lvl, msg in rep)
    no_errors = not any(lvl == "error" for lvl, _ in rep)

    vague = mm_mod.validate(_map([_node("g", "#goal Make it better"), _node("f", "#feature X", y=9)],
                                 [{"fromNode": "g", "toNode": "f"}]))
    done_warn = any(lvl == "warn" and "done" in msg for lvl, msg in vague)
    check("warns on orphans + missing done-criteria, and neither blocks compilation",
          orphan_warn and no_errors and done_warn,
          f"orphan={orphan_warn} clean={no_errors} done={done_warn}")


def t_orphans_kept_on_request():
    """--include-orphans keeps stray nodes instead of silently dropping them."""
    mm = mm_mod.load(FIXTURES / "dark-mode.canvas")
    without = mm_mod.compile_prompt(mm)
    with_ = mm_mod.compile_prompt(mm, include_orphans=True)
    check("orphans excluded by default, preserved under 'Unsorted notes' on request",
          "Unsorted notes" not in without
          and "## Unsorted notes" in with_
          and "Maybe follow the OS preference" in with_)


def t_ignores_non_text_nodes():
    """group/file/link nodes and dangling edges can't break traversal."""
    mm = mm_mod.load(FIXTURES / "dark-mode.canvas")
    ok_nodes = "n_group" not in mm.nodes
    mm2 = _map([_node("g", "#goal Fine\n\nDone = x."), _node("f", "#feature F", y=10)],
               [{"fromNode": "g", "toNode": "ghost"}, {"fromNode": "g", "toNode": "f"}])
    ok_edges = len(mm2.edges) == 1
    check("non-text nodes ignored; edges to missing nodes dropped",
          ok_nodes and ok_edges, f"group_dropped={ok_nodes} dangling_dropped={ok_edges}")


def t_cli_roundtrip():
    """The CLI validates, compiles to a file, and uses exit codes honestly."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "prompt.md"
        rc_c = mm_mod.main(["compile", str(FIXTURES / "dark-mode.canvas"), "-o", str(out)])
        rc_v = mm_mod.main(["validate", str(FIXTURES / "dark-mode.canvas")])
        bad = Path(td) / "bad.canvas"
        bad.write_text(json.dumps({"nodes": [_node("a", "#idea no goal here")]}), encoding="utf-8")
        rc_bad = mm_mod.main(["compile", str(bad)])
        check("CLI: compile writes a file (rc 0), validate warns-only (rc 0), missing goal (rc 1)",
              rc_c == 0 and rc_v == 0 and rc_bad == 1 and out.read_text(encoding="utf-8").startswith("# Add dark mode"),
              f"compile={rc_c} validate={rc_v} bad={rc_bad}")


def t_ai_reply_parsing():
    """`claude -p` is asked for JSON and mostly obliges — but it also fences it,
    prefaces it, or adds a sign-off. Every one of those has to still parse."""
    x = srv_mod._extract_json
    cases = [
        ('{"ideas": ["a", "b"]}', ["a", "b"]),
        ('```json\n{"ideas": ["a", "b"]}\n```', ["a", "b"]),
        ('Here you go:\n{"ideas": ["a", "b"]}\nHope that helps!', ["a", "b"]),
        ('{"ideas": ["a", "b"]}\n\nLet me know if you want more.', ["a", "b"]),
    ]
    ok = all((x(raw) or {}).get("ideas") == want for raw, want in cases)
    check("AI replies parse through fences, preambles and sign-offs", ok,
          str([(r[:24], x(r)) for r, _ in cases]) if not ok else "")
    # Garbage must be None, never a half-built dict the caller would trust.
    check("unparseable AI replies are rejected, not guessed at",
          x("I can't help with that.") is None and x("") is None and x("[1,2]") is None)


def t_ai_prompt_carries_the_map():
    """An idea expanded without its goal is a generic idea. The prompt has to
    carry the map, and it must not leak the JSON contract for the wrong mode."""
    ctx = {"goal": "Ship dark mode", "path": ["Ship dark mode", "Theme toggle"],
           "siblings": ["Colour palette"], "children": ["Persist choice"]}
    p = srv_mod._ai_prompt("expand", "Toggle control", "", ctx, 4)
    check("the expand prompt carries goal, ancestry, siblings and children",
          all(s in p for s in ("Ship dark mode", "Ship dark mode > Theme toggle",
                               "Colour palette", "Persist choice", '{"ideas"')),
          p)
    r = srv_mod._ai_prompt("rewrite", "Toggle control", "", ctx, 4)
    check("rewrite asks for one text field, never an idea list",
          '{"text"' in r and '{"ideas"' not in r, r)
    # An empty map is the common first case; it must not render "None".
    bare = srv_mod._ai_prompt("expand", "Anything", "", {}, 4)
    check("a map with no goal yet still produces a clean prompt",
          "(not written yet)" in bare and "None" not in bare, bare)


def t_ai_prompt_is_anchored_to_the_repo():
    """The reported bug: with the seeded root untouched, `claude` answered a
    real project with "Choose the runtime, language, and key dependencies".
    It had the repo's CLAUDE.md in context all along — the prompt just never
    said to use it, and passed the "Main idea" placeholder off as a real goal."""
    p = srv_mod._ai_prompt("expand", "Toggle", "", {"goal": "Ship dark mode"}, 4)
    check("every prompt demands ideas grounded in THIS repo",
          "repository you are running in" in p and "any codebase" in p, p)

    # "Main idea" is the canvas's seed text, not something the user wrote.
    check("the seeded placeholder is not mistaken for a real goal",
          all(srv_mod._blank(s) for s in ("Main idea", "  MAIN IDEA ", "", "Type something"))
          and not srv_mod._blank("Ship dark mode"))

    empty = srv_mod._ai_prompt("expand", "Main idea", "", {"goal": "Main idea"}, 5)
    check("an untouched map falls back to the project instead of generic advice",
          "The map is still empty" in empty and "Main idea" not in empty, empty)

    # ...but a map with real content must NOT get the fallback, or the node the
    # user actually wrote stops driving the answer.
    real = srv_mod._ai_prompt("expand", "Theme toggle", "", {"goal": "Ship dark mode"}, 5)
    check("a map with real content keeps driving the answer",
          "The map is still empty" not in real and "Theme toggle" in real, real)


CHECKS = [
    t_golden_fixture,
    t_bfs_ownership,
    t_no_duplication_and_cycles_terminate,
    t_reading_order,
    t_kinds_and_default,
    t_constraints_sectioned,
    t_validation_errors,
    t_validation_warns_orphans_and_done,
    t_orphans_kept_on_request,
    t_ignores_non_text_nodes,
    t_cli_roundtrip,
    t_ai_reply_parsing,
    t_ai_prompt_carries_the_map,
    t_ai_prompt_is_anchored_to_the_repo,
]


def main() -> int:
    print("\n  mindmap-prompt harness\n")
    for fn in CHECKS:
        try:
            fn()
        except Exception as exc:  # a crashing check is a failing check
            check(fn.__name__, False, f"raised {exc!r}")
    print()
    if _failures:
        print(f"  {len(_failures)} FAILED:")
        for f in _failures:
            print(f"    - {f}")
        return 1
    print("  ALL GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
