#!/usr/bin/env python3
"""Freshness predicates for agent-memory files (CLAUDE.md and its siblings).

    Every stored fact must be timeless, dated, or a pointer.

This module is the shared, VENDORABLE core behind that rule: pure functions
over (text, repo_root), stdlib only, importing nothing from the other plugin
files. Sibling skills (e.g. memory-hygiene) copy or importlib-load this one
file; neither plugin depends on the other being installed.

Each predicate is grounded in something on disk and detects one *rot class* —
a way a stored fact becomes wrong rather than merely old:

  R1  vanished artifact   — the fact cites a backticked path/class/flag that
                            `git grep` can no longer find anywhere in the tree.
  R2  stale version pin   — the fact states a version for a dependency/tool
                            that a build file in the tree now contradicts
                            (pom.xml, package.json, Cargo.toml, go.mod,
                            pyproject.toml — parsed loosely, stdlib only).
  R3  stale sequence fact — the fact claims "latest/current is `V27`" (any
                            <prefix><N> file-naming scheme) while the tree now
                            contains a higher-numbered sibling.

House rule, inherited from the audit's coverage check and the tuned
freshness-lint this adapts: HIGH PRECISION OVER RECALL. Findings are injected
into session context, so a false positive is a permanent tax on every
conversation. Whenever parsing is uncertain — a version range we can't order,
a name we can't anchor, a numbering scheme the tree doesn't actually use —
the predicate stays silent.

Adapted in part from freshness-lint.py (itself adapted from `freshness_lint.py`
in eugeniughelbur/obsidian-second-brain, MIT (c) 2026 Eugeniu Ghelbur).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time

# ---------------------------------------------------------------------------
# R1 — vanished artifacts
# ---------------------------------------------------------------------------
# What counts as an artifact token worth checking against the tree. Lean
# conservative (high precision) so false positives don't drown the signal.
# Skip URLs, prose-y words, plain numbers, language keywords, anything <4 chars.
ARTIFACT_RE = re.compile(r"`([^`\n]{1,80})`")
ARTIFACT_LOOKS_REAL = re.compile(
    r"^(?:"
    r"[A-Za-z_][\w./\-]*\.(?:java|kt|py|ts|tsx|js|jsx|go|rs|rb|sh|sql|yml|yaml|json|toml|xml|md|adoc|html|css|scss)$"  # filenames
    r"|[A-Za-z_][\w./\-]*/[\w./\-]+"  # paths with a slash
    r"|[A-Z][A-Za-z0-9]*\.[A-Za-z][\w]*"  # ClassName.method or ClassName.FIELD
    r"|--[a-z][a-z0-9-]+"  # --cli-flags
    r"|<[a-z][a-z0-9-]+>"  # <xml-tags>
    r")$"
)


def looks_like_artifact(tok: str) -> bool:
    """R1 filter: is this backticked token concrete enough to ground-check?"""
    tok = tok.strip()
    if len(tok) < 4 or len(tok) > 80:
        return False
    if tok.startswith(("http://", "https://", "git@", "//")):
        return False
    return bool(ARTIFACT_LOOKS_REAL.match(tok))


def artifact_tokens(text: str) -> list[str]:
    """R1: extract the deduped backticked artifact tokens worth checking."""
    toks = [t for t in ARTIFACT_RE.findall(text) if looks_like_artifact(t)]
    return list(dict.fromkeys(toks))  # dedup, preserve order


def missing_artifacts(tokens: list[str], repo_root: str = ".",
                      deadline: float | None = None) -> list[str]:
    """R1: the subset of tokens that appear nowhere in the tracked tree.

    Cheap: one `git grep -qF` per token. Bails out (returns what it has / [])
    if not a git repo, git is missing, or the shared deadline has passed.
    """
    misses: list[str] = []
    for tok in tokens:
        if deadline is not None and time.monotonic() > deadline:
            break
        try:
            r = subprocess.run(
                ["git", "-C", repo_root, "grep", "-qF", "--", tok],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []
        if r.returncode == 1:  # not found
            misses.append(tok)
        elif r.returncode not in (0, 1):  # not a git repo or other error
            return []
    return misses


# ---------------------------------------------------------------------------
# R2 — stale version pins
# ---------------------------------------------------------------------------
# Ground truth comes from the same build files the coverage check trusts
# (BUILD_SIGNALS): a version is only ever *expected* to be current because a
# build file on disk states it. Parsing is loose regex over the raw text —
# good enough for the common shapes, silent on everything else.

# Names for which a dotless single-number claim ("Java 21", "node 20") is
# still a version. For every other name the claim must contain a dot, or it
# is more likely prose ("next 3 steps") than a pin.
_SINGLE_NUMBER_OK = {"java", "jdk", "node", "nodejs", "go", "python"}


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def _vt(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def _parse_spec(raw: str):
    """Parse a build-file version spec → ("exact"|"min", "X.Y.Z") or None.

    None means UNCERTAIN — ranges, wildcards, property references — and an
    uncertain spec silences the whole comparison rather than guessing.
    """
    raw = (raw or "").strip().strip('"').strip("'")
    if not raw or "$" in raw or "*" in raw or "||" in raw or "," in raw:
        return None
    m = re.match(r"(\^|~=|~|>=|==|=)?\s*v?(\d+(?:\.\d+)*)", raw)
    if not m:
        return None
    rest = raw[m.end():]
    if re.match(r"^\.[\dxX]", rest):  # 1.2.x-style wildcard tail
        return None
    if rest and " " in rest:  # "  >=1.2 <2.0" compound range
        return None
    kind = "min" if m.group(1) in ("^", "~", "~=", ">=") else "exact"
    return kind, m.group(2)


def build_versions(repo_root: str = ".") -> dict[str, dict]:
    """R2 ground truth: {normalized name: {"display", "specs": [(raw, file)]}}
    read from the build files at the repo root. Missing/odd files are skipped
    silently — no ground truth simply means the predicate claims nothing."""
    out: dict[str, dict] = {}

    def add(name: str, spec, src: str) -> None:
        if not name or spec is None:
            return
        spec = str(spec).strip()
        n = _norm(name)
        if len(n) < 2 or not spec:
            return
        slot = out.setdefault(n, {"display": name, "specs": []})
        slot["specs"].append((spec, src))

    def read(fname: str) -> str | None:
        p = os.path.join(repo_root, fname)
        if not os.path.isfile(p):
            return None
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                return fh.read()
        except OSError:
            return None

    # pom.xml — parent coordinates + <foo.version> properties.
    txt = read("pom.xml")
    if txt:
        parent = re.search(r"<parent>(.*?)</parent>", txt, re.S)
        if parent:
            a = re.search(r"<artifactId>([^<]+)</artifactId>", parent.group(1))
            v = re.search(r"<version>([^<]+)</version>", parent.group(1))
            if a and v:
                add(a.group(1), v.group(1), "pom.xml")
                if a.group(1).strip().startswith("spring-boot"):
                    add("spring-boot", v.group(1), "pom.xml")
        for m in re.finditer(r"<([A-Za-z][\w-]*(?:\.[\w-]+)*?)\.version>([^<]+)</\1\.version>", txt):
            add(m.group(1), m.group(2), "pom.xml")

    # package.json — real JSON, so parse it as JSON.
    txt = read("package.json")
    if txt:
        try:
            data = json.loads(txt)
        except ValueError:
            data = {}
        if isinstance(data, dict):
            for sect in ("dependencies", "devDependencies", "peerDependencies", "engines"):
                d = data.get(sect)
                if isinstance(d, dict):
                    for k, v in d.items():
                        if isinstance(v, str):
                            add(k, v, "package.json")

    # go.mod — the go directive + require lines.
    txt = read("go.mod")
    if txt:
        m = re.search(r"(?m)^go\s+(\d+\.\d+(?:\.\d+)?)\s*$", txt)
        if m:
            add("go", m.group(1), "go.mod")
        for m in re.finditer(r"(?m)^\s*([\w./-]+)\s+v(\d+\.\d+\.\d+[\w.+-]*)", txt):
            add(m.group(1).rsplit("/", 1)[-1], m.group(2), "go.mod")

    # Cargo.toml / pyproject.toml — section-scoped `name = "version"` lines.
    for fname in ("Cargo.toml", "pyproject.toml"):
        txt = read(fname)
        if not txt:
            continue
        section = ""
        for line in txt.splitlines():
            s = line.strip()
            if s.startswith("["):
                section = s.strip("[]").lower()
                continue
            if "dependencies" not in section:
                continue
            m = (re.match(r'([A-Za-z0-9_.-]+)\s*=\s*"([^"]+)"\s*(?:#.*)?$', s)
                 or re.match(r'([A-Za-z0-9_.-]+)\s*=\s*\{[^}]*version\s*=\s*"([^"]+)"', s))
            if m:
                add(m.group(1), m.group(2), fname)
        if fname == "pyproject.toml":
            m = re.search(r'requires-python\s*=\s*"([^"]+)"', txt)
            if m:
                add("python", m.group(1), fname)
            for m in re.finditer(r'"([A-Za-z][A-Za-z0-9_.-]*)\s*(==|>=|~=)\s*([\w.]+)[^"]*"', txt):
                add(m.group(1), m.group(2) + m.group(3), fname)
    return out


def _contradicts(claim: str, raw_spec: str):
    """One claim vs one spec → True (contradicts) / False (consistent) /
    None (uncertain). Prefix-compatible versions are consistent: a claim of
    `3.5` matches an actual `3.5.10`."""
    parsed = _parse_spec(raw_spec)
    if not parsed:
        return None
    kind, base = parsed
    if claim == base or base.startswith(claim + ".") or claim.startswith(base + "."):
        return False
    try:
        ct, bt = _vt(claim), _vt(base)
    except ValueError:
        return None
    if kind == "min":
        # ">=base": an older claim is contradicted; a newer one might be
        # exactly what is installed — uncertain, stay silent.
        return True if ct < bt else None
    return True


def stale_version_pins(text: str, repo_root: str = ".",
                       versions: dict | None = None,
                       deadline: float | None = None) -> list[dict]:
    """R2: lines that pin `<known dependency/tool> <version>` where every
    parseable build-file spec for that name contradicts the stated version.

    Silent when: the name isn't in a build file, the stated version is
    prefix-compatible with any spec, any spec is unparseable/ranged, or the
    line is struck through (`~~`).
    """
    if deadline is not None and time.monotonic() > deadline:
        return []
    versions = build_versions(repo_root) if versions is None else versions
    if not versions:
        return []
    findings: list[dict] = []
    lines = text.split("\n")
    for norm_name, slot in versions.items():
        if deadline is not None and time.monotonic() > deadline:
            break
        name_rx = re.compile(
            r"\b" + r"[\s._/-]?".join(re.escape(p) for p in norm_name.split())
            + r"\b[\s:=@]{1,3}v?(\d+(?:\.\d+)*)(?!\.?\d)",
            re.I,
        )
        for lineno, line in enumerate(lines, 1):
            if "~~" in line:
                continue  # struck-through = already marked superseded
            m = name_rx.search(line)
            if not m:
                continue
            # An example is an illustration, not a pin: "(e.g. `3.5.10.2` →
            # Spring Boot 3.5.10)" states a timeless scheme, and flagging it
            # would be a false positive (found in calibration, 2026-08).
            before = line[:m.start()].lower()
            if "e.g." in before or "example" in before:
                continue
            claim = m.group(1)
            if "." not in claim and norm_name not in _SINGLE_NUMBER_OK:
                continue  # dotless number after an arbitrary name is prose
            verdicts = [_contradicts(claim, spec) for spec, _ in slot["specs"]]
            # Fire only when every spec parsed AND every one contradicts.
            if verdicts and all(v is True for v in verdicts):
                spec, src = slot["specs"][0]
                findings.append({
                    "name": slot["display"],
                    "stated": claim,
                    "actual": spec,
                    "source": src,
                    "line": lineno,
                })
            break  # one finding per name is enough signal
    return findings


# ---------------------------------------------------------------------------
# R3 — stale sequence facts
# ---------------------------------------------------------------------------
# "latest is `V27`" while V28__… exists in the tree. Grounded two ways before
# it may fire: the claimed <prefix><N> must itself resolve to a real file
# (proof the claim is about this naming scheme at all), and a higher-numbered
# sibling must exist. Anything less is uncertain → silent.
SEQ_CLAIM = re.compile(
    r"\b(latest|newest|current|next)\b[^.\n`]{0,40}"
    r"`([A-Za-z][\w-]{0,24}?)(\d+)(?:__[^`]*)?`",
    re.I,
)

_WALK_SKIP_DIRS = {
    ".git", "node_modules", "target", "build", "dist", "out", "vendor",
    "venv", ".venv", "__pycache__", ".gradle", ".idea", "coverage",
}


def repo_files(repo_root: str = ".", limit: int = 20000) -> list[str]:
    """Relative paths of the repo's files: `git ls-files` when available
    (respects .gitignore), a bounded walk otherwise."""
    try:
        r = subprocess.run(["git", "-C", repo_root, "ls-files", "-z"],
                           capture_output=True, timeout=5)
        if r.returncode == 0 and r.stdout:
            return [f for f in r.stdout.decode(errors="replace").split("\0") if f][:limit]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and d not in _WALK_SKIP_DIRS]
        for f in filenames:
            out.append(os.path.relpath(os.path.join(dirpath, f), repo_root))
            if len(out) >= limit:
                return out
    return out


def stale_sequence_facts(text: str, repo_root: str = ".",
                         files: list[str] | None = None,
                         deadline: float | None = None) -> list[dict]:
    """R3: "latest/current/newest is `<prefix><N>`" claims where the tree has
    a file numbered above N in the same scheme, and "next is `<prefix><N>`"
    claims where <prefix><N> already exists (the "next" already happened).

    Silent when the claimed token doesn't match the tree's file naming at all
    — that means we can't prove the claim is about files.
    """
    if deadline is not None and time.monotonic() > deadline:
        return []
    claims = [(m.group(1).lower(), m.group(2), int(m.group(3)), m.start())
              for m in SEQ_CLAIM.finditer(text)]
    if not claims:
        return []
    if files is None:
        files = repo_files(repo_root)
    basenames = [os.path.basename(f) for f in files]
    findings: list[dict] = []
    for kw, prefix, n, pos in claims:
        if deadline is not None and time.monotonic() > deadline:
            break
        line = text[:pos].count("\n") + 1
        if "~~" in text.split("\n")[line - 1]:
            continue
        rx = re.compile(r"^" + re.escape(prefix) + r"(\d+)(?!\d)")
        hits: dict[int, str] = {}
        for b in basenames:
            m = rx.match(b)
            if m:
                hits.setdefault(int(m.group(1)), b)
        if not hits or n not in hits:
            continue  # scheme not proven in the tree → uncertain → silent
        newest = max(hits)
        if kw == "next":
            # A healthy "next is V28" has no V28 file yet; if it exists the
            # future the entry announced has already arrived.
            findings.append({"keyword": kw, "token": f"{prefix}{n}",
                             "newest": hits[newest] if newest > n else hits[n],
                             "line": line})
        elif newest > n:
            findings.append({"keyword": kw, "token": f"{prefix}{n}",
                             "newest": hits[newest], "line": line})
    return findings
