#!/usr/bin/env python3
"""Audit CLAUDE.md for bloat AND staleness and emit a recommendation as
SessionStart additionalContext.

Wired as a SessionStart hook via .claude/settings.json. Silent only when the
file is healthy on every dimension; emits JSON with
`hookSpecificOutput.additionalContext` when one of the thresholds is crossed:

  - whole-file size over the warn / recommend KB thresholds
    (the actual context-pressure dimension; D&L line/entry counts don't see
    bloat that lives under Conventions / Architecture / Gotchas / etc.)
  - D&L section line count / entry count over their thresholds
  - any entry body over the mega-entry cap (split or collapse candidate)
  - any leading-bold "topic" tag repeated enough times (graduation candidate)
  - STALENESS (predicates shared via freshness.py): any entry citing a
    backticked artifact (path / class / flag) that no longer exists in the
    tree (`git grep -qF` miss); any version pin a build file now contradicts
    (pom.xml / package.json / Cargo.toml / go.mod / pyproject.toml); any
    "latest is `V27`"-style sequence fact the tree has moved past
  - COVERAGE: a build file with no matching command in CLAUDE.md, or a repo with
    many top-level directories and no layout prose — the one check that asks
    whether the essentials are present rather than whether there is too much
  - companion context files (`.claude.local.md`, nested CLAUDE.md) over the size
    threshold — they load into context exactly like the root file

Every threshold is overridable per repo; see DEFAULTS / load_config below.

When the `### Decisions & Learnings` heading is missing, the script does NOT
exit silently anymore — it reports the whole-file size + total dated-bullet
count so projects without the wiring still get a nudge.

Designed to be re-runnable manually:

    python3 scripts/audit-claude-md.py

Prints the JSON recommendation to stdout if anything is flagged; exits 0
either way so a noisy session is never blocked.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import time
from collections import Counter

# Freshness predicates live in the shared, vendorable core beside this file
# (freshness.py) — loaded via importlib so it works both as a plugin (read-only
# cache dir) and as a manual .claude/skills install, regardless of CWD.
_F_SPEC = importlib.util.spec_from_file_location(
    "_freshness",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "freshness.py"),
)
freshness = importlib.util.module_from_spec(_F_SPEC)
_F_SPEC.loader.exec_module(freshness)

CLAUDE_MD = "CLAUDE.md"
LOCAL_MD = ".claude.local.md"
SECTION_HEADING = "### Decisions & Learnings"

# Thresholds — calibrated 2026-06-26 against this author's repos, which is
# exactly why they are overridable. "Concise" is not a universal number: a
# 40 KB CLAUDE.md is bloat in a library and reasonable in a monorepo that
# genuinely has that much load-bearing context. Defaults are a starting point,
# not a verdict.
#
# Resolution order (later wins), matching the prompt-coach convention:
#   these defaults → ~/.claude/evolving-claude-md/config.json
#                  → <repo>/.claude/evolving-claude-md/config.json
T_FILE_WARN_KB = 25
T_FILE_RECOMMEND_KB = 40
T_LINES_WARN = 200
T_LINES_RECOMMEND = 300
T_ENTRIES_WARN = 25
T_ENTRIES_RECOMMEND = 35
T_MEGA_ENTRY_CHARS = 800
T_TOPIC_CLUSTER = 3

CONFIG_REL = os.path.join(".claude", "evolving-claude-md", "config.json")
DEFAULTS: dict[str, object] = {
    "file_warn_kb": T_FILE_WARN_KB,
    "file_recommend_kb": T_FILE_RECOMMEND_KB,
    "lines_warn": T_LINES_WARN,
    "lines_recommend": T_LINES_RECOMMEND,
    "entries_warn": T_ENTRIES_WARN,
    "entries_recommend": T_ENTRIES_RECOMMEND,
    "mega_entry_chars": T_MEGA_ENTRY_CHARS,
    "topic_cluster": T_TOPIC_CLUSTER,
    "layout_min_dirs": 5,
    "coverage": True,      # the upward check (build command, layout)
    "nested": True,        # also size-check nested CLAUDE.md + .claude.local.md
    # --- capture-side checks (issue #37) ---
    "adoption_check": True,       # hand-rolled learnings section, zero D&L entries
    "empty_log_commits": 20,      # empty-log state needs at least this many commits
    "empty_log_docs_ratio": 5,    # ... and docs/ markdown outweighing CLAUDE.md by this
    "docs_recurrence": True,      # self-counting language in docs/ ("the third time")
    "layout_drift": True,         # git-tracked top-level dir unmentioned in CLAUDE.md
    "drift_min_files": 3,         # ... with at least this many tracked files in it
}


def load_config(root: str = ".") -> dict:
    """Defaults, then global, then repo. A malformed or unreadable config is
    ignored rather than fatal — this runs on SessionStart, and a broken config
    file must never be the reason a session starts badly."""
    cfg = dict(DEFAULTS)
    for path in (os.path.join(os.path.expanduser("~"), CONFIG_REL),
                 os.path.join(root, CONFIG_REL)):
        try:
            with open(path) as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                cfg.update({k: v for k, v in loaded.items() if k in DEFAULTS})
        except (OSError, ValueError):
            continue
    return cfg

# Staleness — the predicates themselves (what counts as an artifact token,
# version-pin and sequence-fact detection) live in freshness.py; this file
# only shapes the report. Aliases kept for compatibility with older callers.
ARTIFACT_RE = freshness.ARTIFACT_RE
ARTIFACT_LOOKS_REAL = freshness.ARTIFACT_LOOKS_REAL
looks_like_artifact = freshness.looks_like_artifact
STALENESS_MIN_MISSING = 2  # entry flagged only when ≥2 of its artifact tokens are missing
STALENESS_MAX_REPORT = 5
STALENESS_TIME_BUDGET_S = 2.5  # total wall-clock cap on all git-grep checks

# --- coverage: is the essential content there at all? ------------------------
# Every other check in this file pushes DOWN (bloat, staleness, clustering). A
# file can pass all of them and still be useless — 12 KB, perfectly formatted,
# and never saying how to run the tests. This is the one upward check.
#
# It is grounded in what the repo actually is, not in a generic checklist: the
# build file on disk decides which command we expect to find. No build system
# detected means nothing is claimed, because a docs repo legitimately has no
# build command and a checklist would just cry wolf at it.
BUILD_SIGNALS: list[tuple[str, tuple[str, ...], str]] = [
    # marker file            command tokens that satisfy it        label
    ("pom.xml",              ("mvn", "mvnw"),                      "Maven"),
    ("build.gradle",         ("gradle", "gradlew"),                "Gradle"),
    ("build.gradle.kts",     ("gradle", "gradlew"),                "Gradle"),
    ("Cargo.toml",           ("cargo",),                           "Cargo"),
    ("go.mod",               ("go build", "go test", "go run"),    "Go"),
    ("package.json",         ("npm", "pnpm", "yarn", "bun"),       "Node"),
    ("pyproject.toml",       ("pytest", "python -m", "uv ", "poetry", "tox", "hatch"), "Python"),
    ("Gemfile",              ("bundle", "rake"),                   "Ruby"),
    ("composer.json",        ("composer",),                        "PHP"),
    ("mix.exs",              ("mix ",),                            "Elixir"),
    ("CMakeLists.txt",       ("cmake",),                           "CMake"),
    ("Makefile",             ("make",),                            "Make"),
]
# Layout is only expected once the repo is big enough that it isn't obvious from
# `ls`. Same grounding rule as commands: claim nothing the tree doesn't justify.
LAYOUT_WORDS = ("architecture", "layout", "structure", "directory", "modules",
                "components", "the shape", "how it fits")
LAYOUT_MIN_DIRS = 5
LAYOUT_IGNORE_DIRS = {
    "target", "node_modules", "build", "dist", "out", "venv", ".venv",
    "__pycache__", "vendor", "coverage",
}

# Deliberately NOT checked: a "gotchas" section.
# Measured across 29 real repos with a CLAUDE.md, a gotchas-heading check fired
# on 17 of them — 59%, which is noise rather than signal. Worse, those 17 were
# *exactly* the repos with no Decisions & Learnings log at all, so it was only
# re-detecting "hasn't adopted this skill yet", which the audit already says on
# that path. Gotchas arrive by graduation from the log; the topic-cluster check
# above is the grounded way to prompt for them. Don't re-add this without data.

# Explicit opt-out, kept in CLAUDE.md itself so the decision lives with the file:
#   <!-- audit-skip: commands, layout -->
SKIP_RE = re.compile(r"<!--\s*audit-skip:\s*([^>]+?)\s*-->", re.I)


def coverage_gaps(text: str, root: str = ".", cfg: dict | None = None) -> list[str]:
    """What's missing that an agent would actually need.

    High precision by construction — nothing is expected unless the tree proves
    it applies. A build command is only wanted when a build file is present, and
    a layout section only once there are enough directories to get lost in. On a
    29-repo sample this produced zero false positives.
    """
    cfg = cfg or DEFAULTS
    lower = text.lower()
    skipped = {
        s.strip().lower()
        for m in SKIP_RE.findall(text)
        for s in m.split(",")
    }
    gaps: list[str] = []

    if "commands" not in skipped:
        for marker, tokens, label in BUILD_SIGNALS:
            if not os.path.exists(os.path.join(root, marker)):
                continue
            if not any(t in lower for t in tokens):
                gaps.append(
                    f"no build/test command — this is a {label} project "
                    f"(`{marker}`) but CLAUDE.md never mentions `{tokens[0]}`"
                )
            break  # the first marker found is the project's primary build system

    if "layout" not in skipped and not any(w in lower for w in LAYOUT_WORDS):
        try:
            dirs = [
                d for d in os.listdir(root)
                if os.path.isdir(os.path.join(root, d))
                and not d.startswith(".")
                and d not in LAYOUT_IGNORE_DIRS
            ]
        except OSError:
            dirs = []
        if len(dirs) >= int(cfg["layout_min_dirs"]):
            gaps.append(
                f"nothing on layout — {len(dirs)} top-level directories and "
                f"CLAUDE.md never says where anything lives"
            )
    return gaps


# --- capture-side checks (issue #37): the audit's blind spot was a log that ---
# --- was never written to. These detect knowledge that went somewhere else. ---

# A hand-rolled learnings section: the repo already tried to solve the problem,
# just not in the format the parser reads. Zero-FP by construction — a repo
# either has such a heading or it doesn't.
ADOPTION_HEADING_RE = re.compile(
    r"^#{2,4}\s+.*\b(gotchas?|learnings?|lessons?|hard-won|decisions?|notes to self)\b.*$",
    re.I | re.MULTILINE,
)

# Ordinal self-counting in docs/ — a rule that has proven itself repeatedly in
# prose and never graduated to the file that loads every turn. Anchored on
# recurrence phrasing ("the third time", never "the third file").
RECURRENCE_RE = (
    r"the (second|third|fourth|fifth|sixth|[0-9]+(st|nd|rd|th)) time"
    r"|same mistake again|this keeps happening|for the [0-9N]th time"
)

# Top-level dirs whose meaning is conventional enough that not describing them
# is rarely a gap. Everything else git tracks should be locatable from CLAUDE.md.
DRIFT_EXEMPT_DIRS = {"docs", "doc", "test", "tests", "examples", "example", "scripts"}


def _git_lines(args: list[str], root: str = ".") -> list[str]:
    """Run a git command, return stdout lines; [] on any failure."""
    import subprocess
    try:
        r = subprocess.run(
            ["git", "-C", root, *args],
            capture_output=True, text=True, timeout=3,
        )
        if r.returncode != 0:
            return []
        return [ln for ln in r.stdout.splitlines() if ln]
    except Exception:
        return []


def adoption_candidate(text: str, entry_count: int) -> str | None:
    """A learnings-shaped heading with bullets under it, while the parseable
    D&L log has zero entries — the audit state `unadopted`."""
    if entry_count:
        return None
    for m in ADOPTION_HEADING_RE.finditer(text):
        heading = m.group(0).strip()
        if SECTION_HEADING.lstrip("# ").lower() in heading.lower():
            continue  # the D&L heading itself is the format, not a hand-rolled log
        after = text[m.end():]
        nxt = re.search(r"\n#{1,4} ", after)
        body = after[: nxt.start()] if nxt else after
        bullets = len(re.findall(r"^\s*[-*] ", body, re.MULTILINE))
        if bullets >= 3:
            return (
                f"UNADOPTED hand-rolled log: `{heading.lstrip('# ')}` holds "
                f"{bullets} bullets but 0 are parseable D&L entries — offer the "
                f"migration (each bullet dated + topic-tagged under `{SECTION_HEADING}`)."
            )
    return None


def empty_log_signal(text: str, entry_count: int, root: str = ".",
                     cfg: dict | None = None) -> str | None:
    """Distinguish 'empty' from 'healthy': a repo with real history and a docs/
    tree that dwarfs CLAUDE.md, but no D&L entries — the learning went elsewhere."""
    cfg = cfg or DEFAULTS
    if entry_count:
        return None
    commits = _git_lines(["rev-list", "--count", "HEAD"], root)
    n_commits = int(commits[0]) if commits and commits[0].isdigit() else 0
    if n_commits < int(cfg["empty_log_commits"]):
        return None
    docs_kb = 0.0
    for d in ("docs", "doc"):
        p = os.path.join(root, d)
        if not os.path.isdir(p):
            continue
        for dirpath, dirnames, filenames in os.walk(p):
            dirnames[:] = [x for x in dirnames if x not in NESTED_SKIP_DIRS]
            for fn in filenames:
                if fn.endswith((".md", ".adoc", ".rst")):
                    try:
                        docs_kb += os.path.getsize(os.path.join(dirpath, fn)) / 1024.0
                    except OSError:
                        pass
    claude_kb = max(len(text.encode("utf-8")) / 1024.0, 0.1)
    if docs_kb < float(cfg["empty_log_docs_ratio"]) * claude_kb:
        return None
    return (
        f"EMPTY LOG is not healthy here: {n_commits} commits and "
        f"{docs_kb:.0f} KB of docs vs {claude_kb:.1f} KB of CLAUDE.md, yet 0 D&L "
        f"entries — the learning is going somewhere that doesn't load every turn."
    )


def docs_recurrences(root: str = ".") -> list[str]:
    """Self-counting language in docs — 'the third time X happened' is a rule
    begging to graduate into CLAUDE.md."""
    hits = _git_lines(
        ["grep", "-iEl", RECURRENCE_RE, "--", "docs/*.md", "docs/**/*.md",
         "doc/*.md", "doc/**/*.md"],
        root,
    )
    return sorted(set(hits))[:5]


def layout_drift(text: str, root: str = ".", cfg: dict | None = None,
                 skipped: set[str] | None = None) -> tuple[list[str], list[str]]:
    """Structure drift, both directions (issue #37 review additions):

    - new-dir drift: a git-tracked top-level directory (with enough tracked
      files to matter) whose name appears nowhere in CLAUDE.md;
    - stale-layout: a backticked `dir/` mentioned in CLAUDE.md that no longer
      exists in the tree.

    The plain layout check is one-shot — satisfied forever once any layout
    prose exists. This is the check that keeps the prose tracking the tree.
    """
    cfg = cfg or DEFAULTS
    skipped = skipped or set()
    if "layout-drift" in skipped:
        return [], []
    lower = text.lower()

    # -z: NUL-separated, no C-quoting — a path with spaces or non-ASCII chars
    # would otherwise arrive wrapped in literal quotes (found in calibration).
    counts: dict[str, int] = {}
    raw = _git_lines(["-c", "core.quotePath=false", "ls-files", "-z"], root)
    for path in ("\0".join(raw)).split("\0"):
        if "/" not in path:
            continue
        top = path.split("/", 1)[0]
        counts[top] = counts.get(top, 0) + 1

    unmentioned = [
        d for d, n in sorted(counts.items())
        if n >= int(cfg["drift_min_files"])
        and not d.startswith(".")
        and d not in LAYOUT_IGNORE_DIRS
        and d.lower() not in DRIFT_EXEMPT_DIRS
        and not re.search(r"\b" + re.escape(d.lower()) + r"\b", lower)
    ]

    gone = []
    for tok in set(re.findall(r"`([A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)*/)`", text)):
        if os.path.isdir(os.path.join(root, tok)):
            continue
        # Foreign-path filter (the memory-hygiene calibration lesson): a
        # backticked dir that never existed in THIS repo's history is a path in
        # some other repo (a skill's output dir, an example) — not stale layout.
        if not _git_lines(["log", "-1", "--format=%h", "--", tok], root):
            continue
        gone.append(tok)
    return unmentioned[:6], sorted(gone)[:6]


NESTED_MAX_DEPTH = 3       # deep enough for packages/<x>/<y>/CLAUDE.md, shallow enough to stay fast
NESTED_SKIP_DIRS = {
    ".git", ".idea", ".vscode", "node_modules", "target", "build", "dist",
    "out", "vendor", "venv", ".venv", "__pycache__", ".gradle", ".mvn",
}


def companion_files(root: str = ".") -> list[tuple[str, float]]:
    """Every OTHER context file that costs tokens: `.claude.local.md` and any
    nested CLAUDE.md.

    These load into context exactly like the root file, so bloat in them is the
    same problem measured nowhere. The root file gets the full analysis (that is
    where the log lives); these get a size check, because a nested CLAUDE.md
    rarely carries a Decisions & Learnings section and reporting on five files in
    a SessionStart hook would be its own kind of noise.
    """
    found: list[tuple[str, float]] = []

    local = os.path.join(root, LOCAL_MD)
    if os.path.isfile(local):
        found.append((LOCAL_MD, os.path.getsize(local) / 1024.0))

    root_depth = os.path.abspath(root).rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root):
        depth = os.path.abspath(dirpath).rstrip(os.sep).count(os.sep) - root_depth
        if depth >= NESTED_MAX_DEPTH:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in NESTED_SKIP_DIRS and not d.startswith(".")]
        if dirpath == root:
            continue                      # the root file is analysed in full elsewhere
        if CLAUDE_MD in filenames:
            p = os.path.join(dirpath, CLAUDE_MD)
            rel = os.path.relpath(p, root)
            found.append((rel, os.path.getsize(p) / 1024.0))
    return found


def git_grep_misses(tokens: list[str]) -> list[str]:
    """Compatibility wrapper — the implementation moved to freshness.py."""
    return freshness.missing_artifacts(tokens, ".")


def main() -> int:
    if not os.path.exists(CLAUDE_MD):
        return 0

    cfg = load_config()
    with open(CLAUDE_MD) as f:
        text = f.read()
    file_kb = len(text.encode("utf-8")) / 1024.0

    # Companion context files — same token cost, previously unmeasured.
    companions = companion_files() if cfg["nested"] else []
    heavy = [(n, kb) for n, kb in companions if kb > float(cfg["file_warn_kb"])]

    parts: list[str] = []

    skipped = {
        s.strip().lower()
        for m in SKIP_RE.findall(text)
        for s in m.split(",")
    }

    idx = text.find(SECTION_HEADING)
    if idx == -1:
        # No D&L wiring. Still report file size + total dated bullets so
        # bloat doesn't grow unwatched (the old script returned silently) —
        # and run the capture-side checks: this path is exactly where a log
        # that was never written to hides (issue #37).
        dated_bullets = len(
            re.findall(r"^- (?:~~)?\d{4}-\d{2}-\d{2}", text, re.MULTILINE)
        )
        gaps = coverage_gaps(text, cfg=cfg) if cfg["coverage"] else []
        adoption = adoption_candidate(text, 0) if cfg["adoption_check"] else None
        empty = empty_log_signal(text, 0, cfg=cfg)
        recur = docs_recurrences() if cfg["docs_recurrence"] else []
        drift_new, drift_gone = (
            layout_drift(text, ".", cfg, skipped) if cfg["layout_drift"] else ([], [])
        )
        if (file_kb < float(cfg["file_warn_kb"])
                and dated_bullets < float(cfg["entries_warn"])
                and not gaps and not heavy and not adoption and not empty
                and not recur and not drift_new and not drift_gone):
            return 0
        parts.append(
            f"📝 CLAUDE.md audit: no `{SECTION_HEADING}` section found "
            f"({file_kb:.1f} KB, {dated_bullets} dated bullets elsewhere)."
        )
        if adoption:
            parts.append(f"🔎 {adoption}")
        if empty:
            parts.append(f"🔎 {empty}")
        if recur:
            listed = ", ".join(f"`{p}`" for p in recur[:3])
            parts.append(
                f"🔎 Docs are counting their own recurrences ({listed}) — a rule "
                f"that has proven itself in prose belongs in CLAUDE.md."
            )
        if drift_new:
            parts.append(
                f"🔎 Layout drift — tracked top-level dir"
                f"{'' if len(drift_new) == 1 else 's'} CLAUDE.md never mentions: "
                + ", ".join(f"`{d}/`" for d in drift_new)
                + ". Describe or `<!-- audit-skip: layout-drift -->`."
            )
        if drift_gone:
            parts.append(
                "🔎 Stale layout — mentioned but gone from the tree: "
                + ", ".join(f"`{d}`" for d in drift_gone) + " (removal candidates)."
            )
        if file_kb > float(cfg["file_recommend_kb"]):
            parts.append("**Whole-file compaction RECOMMENDED.**")
        elif file_kb > float(cfg["file_warn_kb"]):
            parts.append("Consider compacting the file.")
        if gaps:
            parts.append(f"Coverage: {'; '.join(gaps)}.")
        if heavy:
            listed = ", ".join(f"`{n}` ({kb:.1f} KB)" for n, kb in sorted(heavy, key=lambda x: -x[1])[:4])
            parts.append(f"Other context files over {cfg['file_warn_kb']} KB: {listed}.")
        parts.append(
            "Wire `evolving-claude-md` (add to `enabledPlugins`) so the file "
            "gets a learning loop instead of growing under one big section."
        )
        out = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": " ".join(parts),
            }
        }
        json.dump(out, sys.stdout)
        return 0

    section = text[idx + len(SECTION_HEADING):]
    next_h3 = re.search(r"\n### ", section)
    if next_h3:
        section = section[: next_h3.start()]

    section_lines = section.count("\n")

    # Entries: a top-level bullet line starting with "- YYYY-MM-DD" (optionally
    # wrapped in ~~...~~ for superseded), followed by the body until the next
    # such bullet (or end of section).
    entry_pat = re.compile(
        r"^- (?:~~)?(\d{4}-\d{2}-\d{2})(?:~~)? — (.+?)(?=\n- (?:~~)?\d{4}-\d{2}-\d{2}|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    entries = entry_pat.findall(section)
    entry_count = len(entries)

    mega = [(d, b.strip()[:90]) for d, b in entries if len(b) > int(cfg["mega_entry_chars"])]

    # Topic clustering by the first bold phrase in the body.
    topics: list[str] = []
    for _, body in entries:
        m = re.match(r"\*\*([^*]+?)\*\*", body)
        if not m:
            continue
        t = m.group(1).strip().lower()
        t = re.sub(r"[.,:;!?]+$", "", t)
        t = re.sub(r"\s*\([^)]*\)\s*$", "", t)
        topics.append(t)
    topic_freq = Counter(topics)
    clusters = sorted(
        ((t, n) for t, n in topic_freq.items() if n >= int(cfg["topic_cluster"])),
        key=lambda x: -x[1],
    )

    # Staleness checks (predicates in freshness.py): per entry, backticked
    # artifact tokens checked against the tree; plus whole-file version-pin
    # and sequence-fact detectors. One shared wall-clock budget across all of
    # them so the hook stays under its 5s timeout even on big files.
    stale: list[tuple[str, str, list[str]]] = []
    deadline = time.monotonic() + STALENESS_TIME_BUDGET_S
    # Newest entries first — they're the most actionable.
    for date, body in reversed(entries):
        if time.monotonic() > deadline:
            break
        toks = freshness.artifact_tokens(body)
        if not toks:
            continue
        miss = freshness.missing_artifacts(toks, ".", deadline=deadline)
        if len(miss) >= STALENESS_MIN_MISSING:
            m = re.match(r"\*\*([^*]+?)\*\*", body)
            hint = m.group(1).strip() if m else body.strip()[:60]
            stale.append((date, hint, miss))
        if len(stale) >= STALENESS_MAX_REPORT * 3:
            break

    # Version pins the build file now contradicts, and "latest is `V27`"-style
    # sequence facts the tree has moved past. Both stay silent when uncertain.
    stale_pins = freshness.stale_version_pins(text, ".", deadline=deadline)
    stale_seqs = freshness.stale_sequence_facts(text, ".", deadline=deadline)

    level: str | None = None
    if (
        file_kb > float(cfg["file_recommend_kb"])
        or section_lines > float(cfg["lines_recommend"])
        or entry_count > float(cfg["entries_recommend"])
    ):
        level = "recommended"
    elif (
        file_kb > float(cfg["file_warn_kb"])
        or section_lines > float(cfg["lines_warn"])
        or entry_count > float(cfg["entries_warn"])
    ):
        level = "consider"

    gaps = coverage_gaps(text, cfg=cfg) if cfg["coverage"] else []

    # Capture-side checks run on this path too: a D&L section with zero
    # entries is still an unwritten log, and drift/recurrence are independent
    # of the log's health entirely.
    adoption = adoption_candidate(text, entry_count) if cfg["adoption_check"] else None
    empty = empty_log_signal(text, entry_count, cfg=cfg)
    recur = docs_recurrences() if cfg["docs_recurrence"] else []
    drift_new, drift_gone = (
        layout_drift(text, ".", cfg, skipped) if cfg["layout_drift"] else ([], [])
    )

    if (not level and not mega and not clusters and not stale
            and not stale_pins and not stale_seqs and not gaps and not heavy
            and not adoption and not empty and not recur
            and not drift_new and not drift_gone):
        return 0

    parts.append(
        f"📝 CLAUDE.md audit ({file_kb:.1f} KB total; {entry_count} entries, "
        f"{section_lines} lines in Decisions & Learnings)."
    )
    if level == "recommended":
        parts.append("**Compaction RECOMMENDED.**")
    elif level == "consider":
        parts.append("Consider compaction.")

    if mega:
        head = "; ".join(f'{d}: "{h}…"' for d, h in mega[:3])
        parts.append(
            f"{len(mega)} mega-entr{'y' if len(mega) == 1 else 'ies'} (>{cfg['mega_entry_chars']} chars): {head}."
        )
    if clusters:
        listed = ", ".join(f'"{t}" ({n})' for t, n in clusters[:5])
        parts.append(
            f"Topic tags with {cfg['topic_cluster']}+ entries (graduation candidates → Conventions/Gotchas): {listed}."
        )
    if stale:
        listed = "; ".join(
            f'{d} "{h}" cites missing {", ".join(f"`{m}`" for m in miss[:3])}'
            for d, h, miss in stale[:STALENESS_MAX_REPORT]
        )
        more = f" (+{len(stale) - STALENESS_MAX_REPORT} more)" if len(stale) > STALENESS_MAX_REPORT else ""
        parts.append(
            f"⚠️ {len(stale)} entr{'y' if len(stale) == 1 else 'ies'} cite vanished artifacts "
            f"(strike/update candidates): {listed}{more}."
        )
    if stale_pins:
        listed = "; ".join(
            f"says `{p['name']} {p['stated']}` but `{p['source']}` has {p['actual']}"
            for p in stale_pins[:STALENESS_MAX_REPORT]
        )
        more = (f" (+{len(stale_pins) - STALENESS_MAX_REPORT} more)"
                if len(stale_pins) > STALENESS_MAX_REPORT else "")
        parts.append(
            f"⚠️ {len(stale_pins)} stale version pin{'' if len(stale_pins) == 1 else 's'} "
            f"(strike/update candidates): {listed}{more}."
        )
    if stale_seqs:
        listed = "; ".join(
            f"says {s['keyword']} is `{s['token']}` but `{s['newest']}` exists"
            for s in stale_seqs[:STALENESS_MAX_REPORT]
        )
        more = (f" (+{len(stale_seqs) - STALENESS_MAX_REPORT} more)"
                if len(stale_seqs) > STALENESS_MAX_REPORT else "")
        parts.append(
            f"⚠️ {len(stale_seqs)} stale sequence fact{'' if len(stale_seqs) == 1 else 's'} "
            f"(strike/update candidates): {listed}{more}."
        )

    if adoption:
        parts.append(f"🔎 {adoption}")
    if empty:
        parts.append(f"🔎 {empty}")
    if recur:
        listed = ", ".join(f"`{p}`" for p in recur[:3])
        parts.append(
            f"🔎 Docs are counting their own recurrences ({listed}) — a rule "
            f"that has proven itself in prose belongs in CLAUDE.md."
        )
    if drift_new:
        parts.append(
            f"🔎 Layout drift — tracked top-level dir"
            f"{'' if len(drift_new) == 1 else 's'} CLAUDE.md never mentions: "
            + ", ".join(f"`{d}/`" for d in drift_new)
            + ". Describe or `<!-- audit-skip: layout-drift -->`."
        )
    if drift_gone:
        parts.append(
            "🔎 Stale layout — mentioned but gone from the tree: "
            + ", ".join(f"`{d}`" for d in drift_gone) + " (removal candidates)."
        )

    if heavy:
        listed = ", ".join(f"`{n}` ({kb:.1f} KB)" for n, kb in sorted(heavy, key=lambda x: -x[1])[:4])
        parts.append(
            f"Other context files over {cfg['file_warn_kb']} KB — they load the same as this one: {listed}."
        )

    if gaps:
        # Deliberately one line and last-but-one: a file can be bloated AND
        # missing the basics, and the basics are the cheaper fix.
        parts.append(
            f"⬆️ Coverage gap — {'; '.join(gaps)}. "
            f"Offer to add it; if it genuinely doesn't apply, add "
            f"`<!-- audit-skip: commands -->` (or the gap's name) to CLAUDE.md so it stops asking."
        )

    parts.append(
        "When work allows, briefly propose a compaction edit to the user — graduate stable topics to Conventions/Gotchas (per skill), split mega-entries (>200 chars body) into docs/decisions/{date}-{topic}.md teasers, strike-through superseded items, and review the staleness candidates (the cited token isn't in the tree — entry may be wrong now). End-of-quarter? Suggest `scripts/archive-decisions.py --cutoff …`."
    )

    out = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": " ".join(parts),
        }
    }
    json.dump(out, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
