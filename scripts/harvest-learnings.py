#!/usr/bin/env python3
"""Harvest universal learnings from consuming repos back into marketplace seeds
(issue #3 — graduation rung 3: repo-core → upstream seed, via a PR).

Harvest, don't sync: most learnings are repo-specific and must stay local.
This tool only *drafts* — the PR is the curation gate, because universal-vs-
local is a human judgment. The strength signal for a candidate is the same
learning surfacing in >= --min-repos distinct repos for the same role.

Read-only over each repo's `.claude/roles/*.md` (crew.md, panel.md,
research.md, per-role core files). Bullets marked `(seed)` are the shipped
seed itself and are excluded — they would trivially self-match.

Usage:
    scripts/harvest-learnings.py                     # report to stdout
    scripts/harvest-learnings.py --draft harvest.md  # write PR-ready draft
    scripts/harvest-learnings.py --root ~/IdeaProjects --min-repos 2 --json
    make harvest
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent

# Where a graduated learning would land, per role source. The draft names the
# target so the human applying it doesn't have to re-derive the mapping.
SEED_TARGETS = {
    "crew.md": "plugins/dev-crew/skills/dev-crew/roles.md (matching role section)",
    "panel.md": "shipped panel seed guidance in plugins/brainstorm-panel/skills/brainstorm-panel/SKILL.md",
    "research.md": "shipped archetype guidance in plugins/research-sweep/skills/research-sweep/SKILL.md",
    "core": "plugins/roles/skills/<role>/role.md  ## Learnings (core)",
}

ROLE_HEAD = re.compile(r"^#{2,3}\s+(.+?)\s*$")
BULLET = re.compile(r"^\s*[-*]\s+(.*\S)\s*$")
LEARN_KEY = re.compile(r"^\s*[-*]\s*learnings:\s*$", re.I)
# Three learnings markers seen in the wild: a `- learnings:` row field
# (crew.md seed style), a `## Learnings` heading (core role files), and a
# bold `**Learnings.**` paragraph lead (research.md registry style).
LEARN_HEAD = re.compile(r"^#{2,3}\s+Learnings\b|^\*\*Learnings\.?\*\*\s*$", re.I)


def extract(path: Path, repo: str) -> list[dict]:
    """(role, bullet, repo, file) for every learnings bullet in a registry or
    core role file. Two shapes: a `- learnings:` field whose sub-bullets
    follow (crew/panel/research rows), and a `## Learnings` heading with
    bullets under it (core role files)."""
    out = []
    role = path.stem if path.name not in ("crew.md", "panel.md", "research.md",
                                          "registry.md") else None
    in_learn = False
    current = role
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    for ln in lines:
        h = ROLE_HEAD.match(ln)
        if h and not LEARN_HEAD.match(ln):
            current = h.group(1).strip().lower()
            in_learn = False
            continue
        if LEARN_KEY.match(ln) or LEARN_HEAD.match(ln):
            in_learn = True
            continue
        if in_learn:
            b = BULLET.match(ln)
            if b:
                text = b.group(1)
                if not text.lower().startswith("(seed)") and "none yet" not in text.lower():
                    out.append({"role": current or path.stem, "text": text,
                                "repo": repo, "file": str(path)})
            elif ln.startswith((" ", "\t")) and ln.strip() and out and \
                    out[-1]["role"] == (current or path.stem):
                out[-1]["text"] += " " + ln.strip()   # wrapped bullet line
            elif ln.strip():
                in_learn = False
    return out


def tokens(text: str) -> set[str]:
    text = re.sub(r"\(20\d\d[^)]*\)", "", text)  # strip dated parentheticals
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) >= 3}


def cluster(items: list[dict], jaccard: float = 0.5) -> list[list[dict]]:
    """Greedy same-role clustering by token overlap."""
    by_role: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_role[it["role"]].append(it)
    clusters = []
    for group in by_role.values():
        used = [False] * len(group)
        for i, a in enumerate(group):
            if used[i]:
                continue
            c = [a]; used[i] = True
            ta = tokens(a["text"])
            for j in range(i + 1, len(group)):
                if used[j]:
                    continue
                tb = tokens(group[j]["text"])
                if ta and tb and len(ta & tb) / len(ta | tb) >= jaccard:
                    c.append(group[j]); used[j] = True
            clusters.append(c)
    return clusters


def selftest() -> int:
    """Synthetic fixture: the same skeptic learning in two repos must cluster
    into exactly one cross-repo candidate; a repo-specific bullet must not."""
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        for repo, extra in (("alpha", "- alpha-only: pin the CI runner image"),
                            ("beta", "")):
            d = Path(t) / repo / ".claude" / "roles"
            d.mkdir(parents=True)
            (d / "crew.md").write_text(
                "### skeptic\n- learnings:\n"
                "  - demand a reproduction before accepting any root cause\n"
                f"  {extra}\n")
        items = []
        for repo in ("alpha", "beta"):
            items.extend(extract(Path(t) / repo / ".claude/roles/crew.md", repo))
        cands = [c for c in cluster(items)
                 if len({x["repo"] for x in c}) >= 2]
        assert len(cands) == 1, f"expected 1 cross-repo cluster, got {len(cands)}"
        assert "reproduction" in cands[0][0]["text"]
    print("harvest selftest: OK")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(Path.home() / "IdeaProjects"))
    ap.add_argument("--min-repos", type=int, default=2)
    ap.add_argument("--jaccard", type=float, default=0.5)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--draft", metavar="FILE")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()

    root = Path(args.root).expanduser()
    items = []
    for repo_dir in sorted(root.iterdir()) if root.is_dir() else []:
        roles_dir = repo_dir / ".claude" / "roles"
        if not roles_dir.is_dir():
            continue
        for f in sorted(roles_dir.glob("*.md")):
            items.extend(extract(f, repo_dir.name))

    clusters = cluster(items, args.jaccard)
    candidates, watching = [], []
    for c in clusters:
        repos = sorted({x["repo"] for x in c})
        entry = {"role": c[0]["role"], "text": c[0]["text"],
                 "repos": repos, "variants": len(c)}
        (candidates if len(repos) >= args.min_repos else watching).append(entry)

    if args.json:
        print(json.dumps({"scanned_bullets": len(items),
                          "candidates": candidates,
                          "watching": len(watching)}, indent=1))
        return 0

    print(f"harvest — {len(items)} learnings bullets across "
          f"{len({i['repo'] for i in items})} repo(s) under {root}")
    if not candidates:
        print(f"  no cross-repo candidates yet (threshold: same learning in "
              f">={args.min_repos} repos); {len(watching)} single-repo "
              f"learnings watching")
    else:
        print(f"  {len(candidates)} candidate(s) for seed graduation:")
        for e in candidates:
            print(f"  · [{e['role']}] {e['text'][:100]}")
            print(f"      seen in: {', '.join(e['repos'])}")

    if args.draft:
        lines = ["# Harvest draft — proposed seed graduations", "",
                 "Apply by hand, then PR with a version bump on each touched "
                 "plugin. Strength signal: same learning in >= "
                 f"{args.min_repos} repos.", ""]
        if not candidates:
            lines.append("_No candidates cleared the bar on this run._")
        for e in candidates:
            lines += [f"## {e['role']}",
                      f"- proposed bullet: {e['text']}",
                      f"- provenance: {', '.join(e['repos'])} ({e['variants']} variant(s))",
                      f"- target: {SEED_TARGETS.get('core')}", ""]
        Path(args.draft).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"  draft written: {args.draft}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
