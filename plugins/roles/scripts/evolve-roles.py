#!/usr/bin/env python3
"""Deep audit of role files in `.claude/roles/` — surfaces refinement
candidates (consolidation, staleness, body-drift, solo→core graduation) as
proposals the user gates. Never silently rewrites a role file.

Usage:
    python3 evolve-roles.py                 # report all roles to stdout
    python3 evolve-roles.py --role skeptic  # one role only
    python3 evolve-roles.py --out audit.md  # write report to file

Runs from the consuming repo's root. Skips consumer registries (crew.md,
panel.md, research.md, registry.md) — those are seat catalogs, not role files.
Uses regex + `git grep` (no LLM). Wall-clock budget-capped so a big
.claude/roles/ tree never stalls a session.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from collections import Counter
from typing import Dict, List, Tuple

ROLES_DIR = os.path.join(".claude", "roles")
CONSUMER_FILES = {"crew.md", "panel.md", "research.md", "registry.md", "audit.md"}
CONSUMER_REGISTRIES = ("crew.md", "panel.md", "research.md")

# Thresholds. Conservative: better to under-flag than to fill the audit with noise.
T_CONSOLIDATE_TOPIC = 3   # ≥N learnings on one topic → consolidation candidate
T_STALENESS_MISSING = 2   # ≥N missing tokens in one learning → staleness candidate
T_DRIFT_LEARNINGS = 3     # ≥N learnings that contradict/extend Body → drift candidate
T_GRADUATE_SOLO = 3       # ≥N solo learnings on one topic → graduation candidate
T_GRADUATE_REGISTRIES = 2 # role appears in ≥N consumer registries → cross-context

STALENESS_BUDGET_S = 4.0  # total wall-clock cap on git-grep calls across all roles


ARTIFACT_RE = re.compile(r"`([^`\n]{1,80})`")
ARTIFACT_LOOKS_REAL = re.compile(
    r"^(?:"
    r"[A-Za-z_][\w./\-]*\.(?:java|kt|py|ts|tsx|js|jsx|go|rs|rb|sh|sql|yml|yaml|json|toml|xml|md|adoc|html|css|scss)$"
    r"|[A-Za-z_][\w./\-]*/[\w./\-]+"
    r"|[A-Z][A-Za-z0-9]*\.[A-Za-z][\w]*"
    r"|--[a-z][a-z0-9-]+"
    r"|<[a-z][a-z0-9-]+>"
    r")$"
)


def looks_like_artifact(tok: str) -> bool:
    tok = tok.strip()
    if len(tok) < 4 or len(tok) > 80:
        return False
    if tok.startswith(("http://", "https://", "git@", "//")):
        return False
    return bool(ARTIFACT_LOOKS_REAL.match(tok))


def git_grep_miss(tok: str) -> bool:
    """True iff the token appears nowhere in the tracked tree, EXCLUDING the
    `.claude/roles/` directory itself (the role files cite their own artifacts,
    so a literal self-reference would always falsely "find" the token). Returns
    False (treat as present) on any git error so we never flag a real artifact
    as stale just because git is missing or the cwd is not a repo."""
    try:
        r = subprocess.run(
            ["git", "grep", "-qF", "--", tok, "--", ":(exclude).claude/roles/"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 1  # 0 = found, 1 = not found, other = error


def parse_sections(text: str) -> Dict[str, str]:
    """Return {heading_text: body_text} for every `## ` section in the role file."""
    out: Dict[str, str] = {}
    parts = re.split(r"^(## .+)$", text, flags=re.M)
    # parts: [pre, heading1, body1, heading2, body2, ...]
    for i in range(1, len(parts) - 1, 2):
        heading = parts[i].strip()[3:].strip()
        body = parts[i + 1]
        out[heading] = body
    return out


def bullet_lines(section: str) -> List[str]:
    """Return one entry per leading-bullet line (strip the `- ` prefix)."""
    return [ln.lstrip()[2:].strip()
            for ln in section.splitlines()
            if ln.lstrip().startswith("- ")]


def topics_of(bullets: List[str]) -> Counter:
    """Cluster bullets by the artifacts they cite. Each bullet contributes its
    set of artifact tokens to the counter; tokens that appear in ≥T bullets
    flag a consolidation/drift cluster."""
    c: Counter = Counter()
    for b in bullets:
        toks = {t for t in ARTIFACT_RE.findall(b) if looks_like_artifact(t)}
        for t in toks:
            c[t] += 1
    return c


def role_names_in_consumer_registries(roles_dir: str) -> Counter:
    """Count consumer registries (crew.md / panel.md / research.md) that
    reference each role name. Role used by ≥2 → cross-context signal."""
    c: Counter = Counter()
    for reg in CONSUMER_REGISTRIES:
        p = os.path.join(roles_dir, reg)
        if not os.path.exists(p):
            continue
        try:
            text = open(p, encoding="utf-8").read()
        except OSError:
            continue
        names = set(re.findall(r"^### ([a-z][a-z0-9-]*)\s*$", text, re.M))
        names |= set(re.findall(r"^\s*-\s*role:\s*([a-z][a-z0-9-]*)\s*$", text, re.M))
        for n in names:
            c[n] += 1
    return c


def audit_role(path: str, role_name: str, cross_context: int, deadline: float) -> List[str]:
    """Return a list of proposal lines for one role file. Empty list = clean."""
    proposals: List[str] = []
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return proposals

    sections = parse_sections(text)
    core = sections.get("Learnings (core)", "")
    solo = sections.get("Learnings (solo)", "")
    body = sections.get("Body", "")
    charter = sections.get("Charter", "")

    core_bullets = bullet_lines(core)
    solo_bullets = bullet_lines(solo)

    # 1. Consolidation candidates in core
    topics = topics_of(core_bullets)
    clusters = [(t, n) for t, n in topics.items() if n >= T_CONSOLIDATE_TOPIC]
    for tok, n in sorted(clusters, key=lambda x: -x[1])[:5]:
        proposals.append(
            f"- **consolidation**: `{tok}` appears in {n} core learnings → "
            f"propose merging into a single rule; strike-through the originals."
        )

    # 2. Staleness candidates: any learning whose cited artifacts mostly aren't in the tree
    for b in core_bullets + solo_bullets:
        if time.monotonic() > deadline:
            break
        toks = list({t for t in ARTIFACT_RE.findall(b) if looks_like_artifact(t)})
        if not toks:
            continue
        misses = [t for t in toks if git_grep_miss(t)]
        if len(misses) >= T_STALENESS_MISSING:
            hint = b[:80] + ("…" if len(b) > 80 else "")
            proposals.append(
                f"- **staleness**: \"{hint}\" cites missing "
                f"{', '.join(f'`{t}`' for t in misses[:3])} — propose strike + "
                f"follow-up if the lesson holds under the renamed artifact."
            )
            if sum(1 for p in proposals if p.startswith("- **staleness**")) >= 5:
                break  # cap per-role staleness output

    # 3. Body drift candidates: count learnings that contradict the Body
    drift_signals = sum(
        1 for b in core_bullets
        if re.search(r"\b(actually|in practice|despite|contrary to|Body (says|claims))\b", b, re.I)
    )
    if drift_signals >= T_DRIFT_LEARNINGS:
        proposals.append(
            f"- **body-drift**: {drift_signals} core learnings contradict or refine the Body "
            f"(\"actually\" / \"in practice\" patterns) → propose Body / Charter refresh; "
            f"show the user which learnings motivated each change."
        )

    # 4. Solo → core graduation candidates
    if cross_context >= T_GRADUATE_REGISTRIES and len(solo_bullets) >= T_GRADUATE_SOLO:
        solo_topics = topics_of(solo_bullets)
        ready = [(t, n) for t, n in solo_topics.items() if n >= T_GRADUATE_SOLO]
        for tok, n in sorted(ready, key=lambda x: -x[1])[:3]:
            proposals.append(
                f"- **graduation**: `{tok}` appears in {n} solo learnings and role is used by "
                f"{cross_context}/3 consumer registries → propose lifting to `Learnings (core)`."
            )

    return proposals


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--role", help="audit only this role (filename without .md)")
    p.add_argument("--out", help="write the report to this file instead of stdout")
    p.add_argument("--apply", action="store_true",
                   help="(reserved) apply user-confirmed proposals; default is report-only")
    args = p.parse_args()

    if not os.path.isdir(ROLES_DIR):
        print(f"no {ROLES_DIR}/ — nothing to audit", file=sys.stderr)
        return 0

    cores = sorted(
        f for f in os.listdir(ROLES_DIR)
        if f.endswith(".md") and f not in CONSUMER_FILES
    )
    if args.role:
        cores = [f for f in cores if f[:-3] == args.role]
        if not cores:
            print(f"role '{args.role}' not found in {ROLES_DIR}/", file=sys.stderr)
            return 2

    registry_uses = role_names_in_consumer_registries(ROLES_DIR)
    deadline = time.monotonic() + STALENESS_BUDGET_S

    report: List[str] = []
    total_proposals = 0
    for f in cores:
        role = f[:-3]
        path = os.path.join(ROLES_DIR, f)
        proposals = audit_role(path, role, registry_uses.get(role, 0), deadline)
        if proposals:
            report.append(f"\n## {role}\n\n")
            report.append("\n".join(proposals) + "\n")
            total_proposals += len(proposals)

    if not report:
        msg = f"audited {len(cores)} role(s) — no refinement candidates surfaced."
        if args.out:
            with open(args.out, "w") as fh:
                fh.write(f"# Roles evolve audit\n\n{msg}\n")
        else:
            print(msg)
        return 0

    header = (
        f"# Roles evolve audit\n\n"
        f"Audited {len(cores)} role(s); surfaced {total_proposals} refinement candidate(s). "
        f"Every proposal is user-gated — review evidence and apply via explicit Edits.\n"
    )
    full = header + "".join(report) + "\n"
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(full)
        print(f"wrote {args.out} ({total_proposals} proposals across {len(cores)} role(s))")
    else:
        sys.stdout.write(full)
    return 0


if __name__ == "__main__":
    sys.exit(main())
