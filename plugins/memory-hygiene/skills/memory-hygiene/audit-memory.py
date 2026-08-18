#!/usr/bin/env python3
"""SessionStart sweep over the agent-written memory directory.

Governs ~/.claude/projects/<project-slug>/memory/ — the per-project memory the
agent loads every session. CLAUDE.md has evolving-claude-md; this is the other
half of the loaded context, and its failure mode is worse: bloat makes an agent
ignore instructions, rot makes it confidently recall something FALSE.

Every check is grounded against the tree — nothing is flagged by pattern alone:
  - vanished artifact: a backticked path/class/flag `git grep` can't find
  - stale version pin: a stated version every build file now contradicts
  - stale sequence fact: "latest is `V27`" when V28__*.sql exists on disk
  - index drift, both directions: MEMORY.md lines pointing at missing files,
    and memory files no index line mentions (invisible to recall)

Output is a FLAG, never a delete. Supersession discipline: strike the wrong
fact through and append a dated correction — an absent memory leads to
abstention, a trimmed one leads to confident re-emission.

Silent when healthy. Emits SessionStart additionalContext JSON when something
needs re-verification; `--report` prints a full human-readable audit instead.
Config (defaults → ~/.claude/memory-hygiene/config.json → <repo>/.claude/
memory-hygiene/config.json; corrupt files are ignored, never fatal):
  min_missing_artifacts  flag a file at this many vanished tokens (default 1)
  time_budget_s          wall-clock cap on all grounding checks (default 2.5)
  max_report             cap on flagged items in the session banner (default 5)
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import time

_F_SPEC = importlib.util.spec_from_file_location(
    "_freshness",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "freshness.py"),
)
freshness = importlib.util.module_from_spec(_F_SPEC)
_F_SPEC.loader.exec_module(freshness)

DEFAULTS = {
    "min_missing_artifacts": 2,
    "time_budget_s": 2.5,
    "max_report": 5,
}

def tree_scoped(tok: str, root: str) -> bool:
    """Memory files are personal and span repos — they legitimately cite other
    repos' paths, external tools' CLI flags, and library symbols. Only tokens
    provably about THIS tree are worth grounding against it; everything else
    is a pointer, and a pointer that can't be checked here is not rot here.

    Keep: paths whose first segment exists in the tree; bare filenames;
    Class.member symbols. Drop: --flags (usually another tool's), <angle>
    placeholders, and paths rooted outside the tree (owner/repo slugs,
    sibling-repo files)."""
    tok = tok.strip()
    if tok.startswith("--") or tok.startswith("<"):
        return False
    if "..." in tok:
        return False  # an abbreviated path can never grep-match — noise only
    if "/" in tok:
        head = tok.lstrip("./").split("/", 1)[0]
        return os.path.isdir(os.path.join(root, head))
    return True


INDEX_LINK = re.compile(r"\[[^\]]+\]\(([^)#]+\.md)\)")


def project_slug(root: str) -> str:
    return re.sub(r"[^A-Za-z0-9-]", "-", os.path.abspath(root))


def memory_dir(root: str, home: str | None = None) -> str:
    home = home or os.path.expanduser("~")
    return os.path.join(home, ".claude", "projects", project_slug(root), "memory")


def load_config(root: str = ".") -> dict:
    cfg = dict(DEFAULTS)
    for path in (
        os.path.join(os.path.expanduser("~"), ".claude", "memory-hygiene", "config.json"),
        os.path.join(root, ".claude", "memory-hygiene", "config.json"),
    ):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                for k in DEFAULTS:
                    if k in data and isinstance(data[k], (int, float)):
                        cfg[k] = data[k]
        except (OSError, json.JSONDecodeError, ValueError):
            continue
    return cfg


def audit(root: str = ".", mem_dir: str | None = None, cfg: dict | None = None) -> dict:
    """Returns {"files": {...per-file findings...}, "index": {...drift...},
    "healthy": bool}. Grounding root is the REPO (facts cite its tree); the
    memory dir is user-global."""
    cfg = cfg or load_config(root)
    mem = mem_dir if mem_dir is not None else memory_dir(root)
    out: dict = {"memory_dir": mem, "files": {}, "index": {}, "healthy": True}
    if not os.path.isdir(mem):
        return out

    deadline = time.monotonic() + float(cfg["time_budget_s"])
    names = sorted(f for f in os.listdir(mem)
                   if f.endswith(".md") and f != "MEMORY.md"
                   and not f.startswith("."))  # skip ._* AppleDouble/hidden junk

    versions = freshness.build_versions(root)
    tree_files = freshness.repo_files(root)

    for name in names:
        path = os.path.join(mem, name)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        finds: dict = {}
        toks = [t for t in freshness.artifact_tokens(text)
                if tree_scoped(t, root)]
        missing = [t for t in freshness.missing_artifacts(toks, root,
                                                          deadline=deadline)
                   if not os.path.exists(os.path.join(root, t))]
        if len(missing) >= cfg["min_missing_artifacts"]:
            finds["vanished"] = missing
        pins = freshness.stale_version_pins(text, root, versions=versions,
                                            deadline=deadline)
        if pins:
            finds["pins"] = pins
        seqs = freshness.stale_sequence_facts(text, root, files=tree_files,
                                              deadline=deadline)
        if seqs:
            finds["sequence"] = seqs
        if finds:
            out["files"][name] = finds

    # Index drift, both directions.
    index_path = os.path.join(mem, "MEMORY.md")
    linked: set[str] = set()
    if os.path.isfile(index_path):
        try:
            with open(index_path, encoding="utf-8") as fh:
                linked = {os.path.basename(m) for m in INDEX_LINK.findall(fh.read())}
        except OSError:
            pass
        dangling = sorted(linked - set(names))
        orphans = sorted(set(names) - linked)
        if dangling:
            out["index"]["dangling"] = dangling  # index → missing file
        if orphans:
            out["index"]["orphans"] = orphans    # file → no index line
    elif names:
        out["index"]["no_index"] = True          # memories exist, nothing loads them

    out["healthy"] = not out["files"] and not out["index"]
    return out


def banner(result: dict, cfg: dict) -> str:
    parts = ["📇 memory-hygiene:"]
    items = []
    for name, finds in result["files"].items():
        bits = []
        if "vanished" in finds:
            bits.append("cites vanished " + ", ".join(f"`{t}`" for t in finds["vanished"][:2]))
        for p in finds.get("pins", []):
            bits.append(f"pins {p['name']} {p['stated']} but {p['source']} has {p['actual']}")
        for s in finds.get("sequence", []):
            bits.append(f"says {s['keyword']} is `{s['token']}` but tree has `{s['newest']}`")
        items.append(f"{name}: " + "; ".join(bits))
    idx = result["index"]
    if idx.get("dangling"):
        items.append("MEMORY.md links missing files: " + ", ".join(idx["dangling"][:3]))
    if idx.get("orphans"):
        items.append(f"{len(idx['orphans'])} memory file(s) not in the MEMORY.md index (invisible to recall): "
                     + ", ".join(idx["orphans"][:3]))
    if idx.get("no_index"):
        items.append("memory files exist but there is no MEMORY.md index")
    shown = items[: cfg["max_report"]]
    parts.append(f"{len(items)} rot candidate(s) in agent memory — re-verify, then strike-through + dated correction (never delete):")
    parts.extend("· " + i for i in shown)
    if len(items) > len(shown):
        parts.append(f"· …(+{len(items) - len(shown)} more — run the memory audit for the full list)")
    return " ".join(parts)


def main(argv: list[str]) -> int:
    root = next((a for a in argv[1:] if not a.startswith("-")), ".")
    cfg = load_config(root)
    result = audit(root, cfg=cfg)

    if "--json" in argv:
        print(json.dumps(result, indent=1))
        return 0
    if "--report" in argv:
        if result["healthy"]:
            print(f"memory-hygiene: {result['memory_dir']} — healthy, nothing to flag")
            return 0
        print(banner(result, dict(cfg, max_report=999)).replace(" · ", "\n  · "))
        return 0
    if result["healthy"]:
        return 0
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": banner(result, cfg),
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
