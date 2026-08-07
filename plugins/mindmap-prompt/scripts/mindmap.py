#!/usr/bin/env python3
"""mindmap-prompt — compile a JSON Canvas mind map into an organized prompt.

The map is a general directed graph of idea nodes. One `#goal` node is the entry
point; everything else hangs off it. Compilation is deterministic — no LLM, no
network — so the same map always yields the same prompt.

Two entry points:

    mindmap.py validate <map.canvas>
    mindmap.py compile  <map.canvas> [--include-orphans] [-o out.md]

Save format is JSON Canvas 1.0 (https://jsoncanvas.org): the top level holds two
optional arrays, `nodes` and `edges`. Node `type` is constrained to
text|file|link|group, so there is no room for a custom kind — instead a node's
kind is a leading Markdown tag in its text (`#goal`, `#constraint`, ...), which
survives a round-trip through Obsidian and stays readable in a git diff.

v1 ships four kinds (goal / feature / idea / constraint). Context, question and
output kinds are deliberately deferred until real use argues for them.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict, deque
from pathlib import Path

# --------------------------------------------------------------------------
# Kinds
# --------------------------------------------------------------------------

# v1 lean set. Order matters: it is the order kinds are documented and offered.
KINDS = ("goal", "feature", "idea", "constraint")
DEFAULT_KIND = "idea"

# A kind tag is a leading `#kind` token on the node's first line.
_TAG_RE = re.compile(r"^\s*#(" + "|".join(KINDS) + r")\b[ \t]*", re.IGNORECASE)

# Words that suggest the goal actually states what "done" means. Deliberately
# small and boring — this mirrors prompt-coach's no-definition-of-done rule, and
# a warning here is a nudge, never a blocker.
_DONE_HINTS = re.compile(
    r"\b(done|acceptance|accept|success|criteria|verif\w*|passes|should\s+\w+|so\s+that)\b",
    re.IGNORECASE,
)

MAX_HEADING = 6


def parse_node_text(raw: str) -> tuple[str, str, str]:
    """Split a node's Markdown into (kind, title, body).

    The kind tag is stripped. The first non-empty line becomes the title; the
    rest is the body, verbatim.
    """
    text = raw or ""
    kind = DEFAULT_KIND
    m = _TAG_RE.match(text)
    if m:
        kind = m.group(1).lower()
        text = text[m.end():]
    text = text.strip()
    if not text:
        return kind, "", ""
    parts = text.split("\n", 1)
    return kind, parts[0].strip(), (parts[1].strip() if len(parts) > 1 else "")


# --------------------------------------------------------------------------
# The map
# --------------------------------------------------------------------------


class MindMap:
    """A parsed JSON Canvas, indexed for traversal.

    Only `text` nodes participate: file/link/group nodes carry no idea content,
    and edges pointing at a dropped node are dropped with it so traversal can
    never dereference a missing id.
    """

    def __init__(self, data: dict):
        raw_nodes = data.get("nodes") or []
        raw_edges = data.get("edges") or []

        self.nodes: dict[str, dict] = {}
        for n in raw_nodes:
            if not isinstance(n, dict) or n.get("type") != "text":
                continue
            nid = n.get("id")
            if not nid:
                continue
            kind, title, body = parse_node_text(n.get("text", ""))
            self.nodes[nid] = {
                "id": nid,
                "kind": kind,
                "title": title,
                "body": body,
                "x": _num(n.get("x")),
                "y": _num(n.get("y")),
            }

        self.edges = []
        for e in raw_edges:
            if (isinstance(e, dict)
                    and e.get("fromNode") in self.nodes
                    and e.get("toNode") in self.nodes):
                # Stable internal key: edge `id` is optional in practice and can
                # repeat, but traversal needs to identify one specific edge.
                e = dict(e, _k=len(self.edges))
                self.edges.append(e)

        self._children: dict[str, list[dict]] = defaultdict(list)
        for e in self.edges:
            self._children[e["fromNode"]].append(e)
        # Reading order: the way the user laid it out on the canvas IS the
        # intended order, so sort each node's children top-to-bottom then
        # left-to-right. No manual re-ordering step for the user.
        for eid in self._children:
            self._children[eid].sort(
                key=lambda e: (self.nodes[e["toNode"]]["y"], self.nodes[e["toNode"]]["x"])
            )

    def children(self, nid: str) -> list[dict]:
        return self._children.get(nid, [])

    def of_kind(self, kind: str) -> list[dict]:
        return sorted(
            (n for n in self.nodes.values() if n["kind"] == kind),
            key=lambda n: (n["y"], n["x"]),
        )

    def goals(self) -> list[dict]:
        return self.of_kind("goal")

    def reachable(self, start: str) -> set[str]:
        """Every node reachable from `start`, following edges in any labelled or
        unlabelled form. Visited-tracking makes cycles terminate."""
        seen: set[str] = set()
        stack = [start]
        while stack:
            nid = stack.pop()
            if nid in seen:
                continue
            seen.add(nid)
            stack.extend(e["toNode"] for e in self.children(nid))
        return seen

    def has_cycle(self) -> bool:
        colour: dict[str, int] = {}  # 1 = on stack, 2 = done

        def visit(nid: str) -> bool:
            colour[nid] = 1
            for e in self.children(nid):
                t = e["toNode"]
                c = colour.get(t, 0)
                if c == 1 or (c == 0 and visit(t)):
                    return True
            colour[nid] = 2
            return False

        return any(colour.get(nid, 0) == 0 and visit(nid) for nid in self.nodes)


def _num(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def load(path: str | Path) -> MindMap:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("not a JSON Canvas file: top level must be an object")
    return MindMap(data)


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def validate(mm: MindMap) -> list[tuple[str, str]]:
    """Return [(level, message)] where level is error | warn | info.

    Errors block compilation. Warnings are advisory: the map still compiles, but
    the user is told what the prompt will be missing. Nothing is ever silently
    dropped.
    """
    out: list[tuple[str, str]] = []

    if not mm.nodes:
        out.append(("error", "the map is empty — no text nodes"))
        return out

    goals = mm.goals()
    if len(goals) == 0:
        out.append(("error", "no #goal node — mark the node that states the task"))
    elif len(goals) > 1:
        titles = ", ".join(f'"{g["title"] or g["id"]}"' for g in goals[:4])
        out.append(("error", f"{len(goals)} #goal nodes ({titles}) — the compiler needs exactly one"))

    for n in sorted(mm.nodes.values(), key=lambda n: (n["y"], n["x"])):
        if not n["title"]:
            out.append(("error", f'node "{n["id"]}" has no text'))

    if len(goals) == 1:
        goal = goals[0]
        if not mm.children(goal["id"]):
            out.append(("error", f'the goal "{goal["title"]}" has no connections — nothing to compile'))

        if not _DONE_HINTS.search(goal["title"] + "\n" + goal["body"]):
            out.append((
                "warn",
                f'the goal "{goal["title"]}" does not say what "done" looks like '
                "— add acceptance criteria to its body",
            ))

        orphans = [n for nid, n in mm.nodes.items() if nid not in mm.reachable(goal["id"])]
        # Constraints are collected as their own section, so an unconnected
        # constraint is intentional, not a stray.
        orphans = [n for n in orphans if n["kind"] != "constraint"]
        if orphans:
            names = ", ".join(f'"{n["title"] or n["id"]}"' for n in orphans[:4])
            more = f" (+{len(orphans) - 4} more)" if len(orphans) > 4 else ""
            out.append((
                "warn",
                f"{len(orphans)} node(s) not connected to the goal: {names}{more} "
                "— connect them, or compile with --include-orphans to keep them",
            ))

    if mm.has_cycle():
        out.append(("warn", "the map has a cycle — repeated nodes compile to a reference, not a copy"))

    if not mm.of_kind("constraint"):
        out.append(("info", "no #constraint nodes — consider naming what must NOT change"))

    return out


# --------------------------------------------------------------------------
# Compilation
# --------------------------------------------------------------------------


def compile_prompt(mm: MindMap, include_orphans: bool = False) -> str:
    """Linearize the map into an organized Markdown prompt.

    A general graph has no inherent document order, so compilation builds a
    **BFS spanning tree** from the goal: every node is owned by its
    shortest-path parent, ties broken by canvas reading order. That guarantees a
    node wired straight to the goal stays a top-level section — a plain DFS
    would let a long branch reach it first and bury it several levels deep.

    Every edge outside that tree (cross-link, back-edge, second parent) renders
    as a `see "..."` reference rather than a copy. So nothing is duplicated,
    nothing is lost, and cycles terminate.
    """
    goals = mm.goals()
    if len(goals) != 1:
        raise ValueError("compile requires exactly one #goal node — run validate first")
    goal = goals[0]

    lines: list[str] = [f"# {goal['title']}"]
    if goal["body"]:
        lines += ["", goal["body"]]

    # Pass 1 — BFS spanning tree. Constraints are skipped: they compile into
    # their own section, not the body.
    owner: dict[str, str] = {goal["id"]: ""}
    tree_edges: set[int] = set()
    queue = deque([goal["id"]])
    while queue:
        nid = queue.popleft()
        for e in mm.children(nid):  # already in reading order
            t = e["toNode"]
            if mm.nodes[t]["kind"] == "constraint" or t in owner:
                continue
            owner[t] = nid
            tree_edges.add(e["_k"])
            queue.append(t)

    # Pass 2 — render the tree depth-first, in reading order.
    body: list[str] = []

    def walk(nid: str, depth: int) -> None:
        for e in mm.children(nid):
            target = mm.nodes[e["toNode"]]
            if target["kind"] == "constraint":
                continue
            label = (e.get("label") or "").strip()
            suffix = f" _({label})_" if label else ""

            if e["_k"] not in tree_edges:
                body.append("")
                body.append(f'→ see "{target["title"]}"{suffix}')
                continue

            hashes = "#" * min(depth + 1, MAX_HEADING)
            body.append("")
            body.append(f"{hashes} {target['title']}{suffix}")
            if target["body"]:
                body.append("")
                body.append(target["body"])
            walk(target["id"], depth + 1)

    walk(goal["id"], 1)
    lines += body
    visited = set(owner)

    constraints = mm.of_kind("constraint")
    if constraints:
        lines += ["", "## Constraints", ""]
        for c in constraints:
            detail = f" — {c['body'].splitlines()[0].strip()}" if c["body"] else ""
            lines.append(f"- {c['title']}{detail}")

    if include_orphans:
        loose = [
            n for nid, n in sorted(mm.nodes.items(), key=lambda kv: (kv[1]["y"], kv[1]["x"]))
            if nid not in visited and n["kind"] != "constraint"
        ]
        if loose:
            lines += ["", "## Unsorted notes", ""]
            for n in loose:
                detail = f" — {n['body'].splitlines()[0].strip()}" if n["body"] else ""
                lines.append(f"- {n['title']}{detail}")

    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _print_report(report: list[tuple[str, str]]) -> None:
    marks = {"error": "✗", "warn": "!", "info": "·"}
    for level, msg in report:
        print(f"  {marks.get(level, '·')} {level}: {msg}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mindmap", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="check a map is prompt-ready")
    v.add_argument("canvas")

    c = sub.add_parser("compile", help="compile a map into an organized prompt")
    c.add_argument("canvas")
    c.add_argument("--include-orphans", action="store_true",
                   help="keep nodes that aren't connected to the goal (under 'Unsorted notes')")
    c.add_argument("-o", "--out", help="write to a file instead of stdout")

    args = ap.parse_args(argv)

    try:
        mm = load(args.canvas)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"cannot read {args.canvas}: {exc}", file=sys.stderr)
        return 2

    report = validate(mm)
    errors = [r for r in report if r[0] == "error"]

    if args.cmd == "validate":
        if report:
            _print_report(report)
        else:
            print("  ✓ map is prompt-ready", file=sys.stderr)
        return 1 if errors else 0

    if errors:
        print("cannot compile — fix these first:", file=sys.stderr)
        _print_report(errors)
        return 1
    # Warnings don't block, but the user should still see them.
    _print_report([r for r in report if r[0] != "error"])

    out = compile_prompt(mm, include_orphans=args.include_orphans)
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
        print(f"  ✓ wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
