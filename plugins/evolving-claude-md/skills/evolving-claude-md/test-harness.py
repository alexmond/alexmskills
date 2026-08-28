#!/usr/bin/env python3
"""evolving-claude-md release gate — run with `make test-evolve`.

Focused on the coverage check, because that is the part with tuning decisions
in it. Half the checks assert that nothing fires: this audit's output is
injected into *every* session's context, so a false positive is not a wrong
answer, it is a permanent tax on every conversation in the repo.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("_audit", HERE / "audit-claude-md.py")
audit = importlib.util.module_from_spec(_spec)
sys.modules["_audit"] = audit
_spec.loader.exec_module(audit)

_failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✓' if ok else '✗'} {name}")
    if not ok:
        _failures.append(name)
        if detail:
            print(f"      {detail}")


def repo(tmp: Path, name: str, claude_md: str, files=(), dirs=()) -> Path:
    d = tmp / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "CLAUDE.md").write_text(claude_md, encoding="utf-8")
    for f in files:
        (d / f).write_text("", encoding="utf-8")
    for x in dirs:
        (d / x).mkdir(exist_ok=True)
    return d


FULL = "# proj\n\n## Architecture\nlayers.\n\nRun `./mvnw test` to verify.\n"


# --------------------------------------------------------------------------

def t_command_gap_is_grounded_in_the_build_file():
    """The whole point: a command is expected only when the tree proves one
    exists. Otherwise a docs repo gets nagged for a build it doesn't have."""
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        maven = repo(tmp, "maven", "# proj\n\n## Architecture\nlayers.\n", ["pom.xml"])
        prose = repo(tmp, "prose", "# notes\n\n## Architecture\nchapters.\n")
        g_maven = audit.coverage_gaps((maven / "CLAUDE.md").read_text(), str(maven))
        g_prose = audit.coverage_gaps((prose / "CLAUDE.md").read_text(), str(prose))
        check("a build file with no command in CLAUDE.md is a gap",
              len(g_maven) == 1 and "Maven" in g_maven[0], str(g_maven))
        check("a repo with no build system is never asked for a command",
              g_prose == [], str(g_prose))


def t_command_gap_clears_when_mentioned():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        for body, label in (("Run `./mvnw verify`.", "wrapper"), ("Use `mvn -q test`.", "bare mvn")):
            r = repo(tmp, f"m-{label.replace(' ','')}",
                     f"# proj\n\n## Architecture\nlayers.\n\n{body}\n", ["pom.xml"])
            got = audit.coverage_gaps((r / "CLAUDE.md").read_text(), str(r))
            check(f"mentioning the command clears the gap ({label})", got == [], str(got))


def t_every_build_system_is_detectable():
    """A marker that never resolves is worse than no entry — it silently means
    'this ecosystem is exempt'."""
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        bad = []
        for i, (marker, tokens, label) in enumerate(audit.BUILD_SIGNALS):
            r = repo(tmp, f"b{i}", "# p\n\n## Architecture\nx.\n", [marker])
            miss = audit.coverage_gaps((r / "CLAUDE.md").read_text(), str(r))
            hit = audit.coverage_gaps(
                f"# p\n\n## Architecture\nx.\n\nRun `{tokens[0]}` here.\n", str(r))
            if not miss or hit:
                bad.append(f"{marker}({label})")
        check(f"all {len(audit.BUILD_SIGNALS)} build systems fire and clear correctly",
              not bad, "broken: " + ", ".join(bad))


def t_layout_gap_needs_a_complex_tree():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        flat = repo(tmp, "flat", "# p\n\nJust a script.\n", dirs=["src"])
        big = repo(tmp, "big", "# p\n\nJust a script.\n",
                   dirs=[f"d{i}" for i in range(audit.LAYOUT_MIN_DIRS)])
        check("a small repo is not asked to document its layout",
              audit.coverage_gaps((flat / "CLAUDE.md").read_text(), str(flat)) == [])
        g = audit.coverage_gaps((big / "CLAUDE.md").read_text(), str(big))
        check("a repo with many top-level dirs and no layout prose is a gap",
              len(g) == 1 and "layout" in g[0], str(g))


def t_build_output_dirs_dont_count_as_layout():
    """`target/` and `node_modules/` are not structure the reader needs told."""
    with tempfile.TemporaryDirectory() as t:
        r = repo(Path(t), "noisy", "# p\n\nJust a script.\n",
                 dirs=["src", "target", "node_modules", "build", "dist", "out"])
        got = audit.coverage_gaps((r / "CLAUDE.md").read_text(), str(r))
        check("generated directories are excluded from the layout count",
              got == [], str(got))


def t_audit_skip_opts_out():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        r = repo(tmp, "skipped",
                 "# p\n\n## Architecture\nx.\n\n<!-- audit-skip: commands -->\n", ["pom.xml"])
        both = repo(tmp, "both", "# p\n\n<!-- audit-skip: commands, layout -->\n",
                    ["pom.xml"], [f"d{i}" for i in range(6)])
        check("audit-skip silences a named gap",
              audit.coverage_gaps((r / "CLAUDE.md").read_text(), str(r)) == [])
        check("audit-skip takes a comma-separated list",
              audit.coverage_gaps((both / "CLAUDE.md").read_text(), str(both)) == [])


def t_a_good_claude_md_is_silent():
    """The assertion that protects every session in every repo."""
    with tempfile.TemporaryDirectory() as t:
        r = repo(Path(t), "good", FULL, ["pom.xml"], [f"d{i}" for i in range(8)])
        got = audit.coverage_gaps((r / "CLAUDE.md").read_text(), str(r))
        check("a CLAUDE.md that covers commands + layout produces nothing", got == [], str(got))


def t_no_regression_on_real_repos():
    """Calibration, pinned. These checks fired zero times across 29 real repos
    with a CLAUDE.md; an edit that makes them chatty should fail here, not in
    someone's session. Skips cleanly when the sample isn't on this machine."""
    sample = sorted(p for p in Path.home().joinpath("IdeaProjects").iterdir()
                    if (p / "CLAUDE.md").is_file()) if Path.home().joinpath("IdeaProjects").is_dir() else []
    if len(sample) < 5:
        check("no false positives across the local repo sample", True, "sample absent — skipped")
        return
    fired = {p.name: g for p in sample
             if (g := audit.coverage_gaps((p / "CLAUDE.md").read_text(errors="replace"), str(p)))}
    check(f"no false positives across {len(sample)} real repos", not fired,
          "; ".join(f"{k}: {v}" for k, v in list(fired.items())[:4]))

    # Freshness detectors, same bar. A fixed repo allowlist proved wrong within
    # hours of the 2026-08 calibration — venice-vr genuinely rotted (pom moved
    # to Boot 4.1.0, CLAUDE.md still said 4.0.6) and the pinned set called that
    # true positive a regression. The durable invariant isn't WHICH repos fire,
    # it's that every hit is a REAL contradiction: the stated version must not
    # be prefix-compatible with the build file's actual version.
    bogus = {}
    for p_ in sample:
        for hit in audit.freshness.stale_version_pins(
                (p_ / "CLAUDE.md").read_text(errors="replace"), str(p_)):
            stated, actual = str(hit["stated"]), str(hit["actual"])
            if actual == stated or actual.startswith(stated + "."):
                bogus.setdefault(p_.name, []).append(hit)
    check(f"every version-pin hit across {len(sample)} real repos is a genuine contradiction",
          not bogus, str(bogus))
    seq_fired = {p.name for p in sample
                 if audit.freshness.stale_sequence_facts(
                     (p / "CLAUDE.md").read_text(errors="replace"), str(p))}
    check(f"sequence-fact detector stays silent across {len(sample)} real repos",
          not seq_fired, f"fired: {sorted(seq_fired)}")


def t_version_pin_is_grounded_in_the_build_file():
    """R2: a stated version is only ever stale because a build file on disk
    contradicts it — fire on contradiction, silent when current."""
    with tempfile.TemporaryDirectory() as t:
        r = Path(t)
        (r / "package.json").write_text(json.dumps({"dependencies": {"react": "18.2.0"}}))
        (r / "pom.xml").write_text(
            "<project><parent><artifactId>spring-boot-starter-parent</artifactId>"
            "<version>3.5.16</version></parent>"
            "<properties><java.version>21</java.version></properties></project>")
        F = audit.freshness
        got = F.stale_version_pins("- 2026-01-01 — **ui** — pinned react 17.0 for legacy.", str(r))
        check("a version pin the build file contradicts fires",
              len(got) == 1 and got[0]["name"] == "react" and got[0]["stated"] == "17.0", str(got))
        check("a version pin matching the build file is silent",
              F.stale_version_pins("we run react 18 and Java 21 here.", str(r)) == [])
        check("a prefix-compatible pin (3.5 vs 3.5.16) is silent",
              F.stale_version_pins("built on Spring Boot 3.5.", str(r)) == [])
        check("a contradicted Spring Boot pin fires via the parent alias",
              any(p["name"] == "spring-boot"
                  for p in F.stale_version_pins("built on Spring Boot 3.4.", str(r))))
        check("a struck-through pin is already handled — silent",
              F.stale_version_pins("~~react 17.0 legacy~~", str(r)) == [])
        check("an example ('e.g. …') is an illustration, not a pin — silent",
              F.stale_version_pins("scheme (e.g. `x` → Spring Boot 3.4).", str(r)) == [])


def t_version_pin_stays_silent_when_uncertain():
    """High precision over recall: wildcard/range specs, dotless numbers after
    arbitrary names, and unknown names must all stay silent."""
    with tempfile.TemporaryDirectory() as t:
        r = Path(t)
        (r / "package.json").write_text(json.dumps(
            {"dependencies": {"next": "*", "vue": "^3.4.0"}, "engines": {"node": ">=18"}}))
        F = audit.freshness
        check("a wildcard spec is uncertain — silent even on mismatch",
              F.stale_version_pins("we pinned next 12.0 back then.", str(r)) == [])
        check("a claim above a ^/>= floor could be what's installed — silent",
              F.stale_version_pins("vue 3.6 and node 20 in use.", str(r)) == [])
        check("a claim below a ^/>= floor is contradicted — fires",
              len(F.stale_version_pins("vue 3.2 in use.", str(r))) == 1)
        check("prose numbers after a dependency-named word are not pins",
              F.stale_version_pins("the next 3 steps happen after react conf 2024.", str(r)) == [])
        check("a version for a name in no build file claims nothing",
              F.stale_version_pins("uses left-pad 1.0.0 heavily.", str(r)) == [])


def t_sequence_fact_is_grounded_in_the_tree():
    """R3: 'latest is `V27`' fires only when V27 itself resolves to a file
    (the scheme is proven) AND a higher-numbered sibling exists."""
    with tempfile.TemporaryDirectory() as t:
        r = Path(t)
        mig = r / "src" / "db" / "migration"
        mig.mkdir(parents=True)
        (mig / "V27__init.sql").write_text("x")
        (mig / "V28__more.sql").write_text("x")
        F = audit.freshness
        got = F.stale_sequence_facts("latest migration is `V27`.", str(r))
        check("'latest is V27' with V28 on disk fires",
              len(got) == 1 and got[0]["token"] == "V27" and "V28" in got[0]["newest"], str(got))
        check("'next is V28' when V28 already exists fires",
              len(F.stale_sequence_facts("next is `V28` to write.", str(r))) == 1)
        check("'latest is V28' (actually the newest) is silent",
              F.stale_sequence_facts("latest migration is `V28`.", str(r)) == [])
        check("a struck-through sequence claim is silent",
              F.stale_sequence_facts("~~latest migration is `V27`~~", str(r)) == [])


def t_sequence_fact_stays_silent_when_uncertain():
    with tempfile.TemporaryDirectory() as t:
        r = Path(t)
        (r / "V27__init.sql").write_text("x")
        F = audit.freshness
        check("a prefix the tree doesn't use claims nothing",
              F.stale_sequence_facts("latest is `Q99` in the queue.", str(r)) == [])
        check("'next is V28' before V28 exists is healthy — silent",
              F.stale_sequence_facts("next is `V28` to write.", str(r)) == [])
        check("dotted versions are pins, not sequences — never matched",
              F.stale_sequence_facts("latest is `v1.2.3` release.", str(r)) == [])
        check("a claim with no latest/current/next keyword is not a claim",
              F.stale_sequence_facts("see `V27__init.sql` for the shape.", str(r)) == [])


def t_vanished_artifact_predicate_moved_to_freshness():
    """R1 moved (not duplicated) into freshness.py; grounded via git grep."""
    F = audit.freshness
    check("audit re-exports the freshness artifact predicates",
          audit.looks_like_artifact is F.looks_like_artifact
          and audit.ARTIFACT_RE is F.ARTIFACT_RE)
    check("artifact_tokens filters and dedups like the old inline code",
          F.artifact_tokens("see `a/b/c.py` and `a/b/c.py` and `word` and `x`")
          == ["a/b/c.py"])
    with tempfile.TemporaryDirectory() as t:
        r = Path(t)
        (r / "kept.py").write_text("real content")
        try:
            subprocess.run(["git", "-C", str(r), "init", "-q"], check=True, timeout=10)
            subprocess.run(["git", "-C", str(r), "add", "-A"], check=True, timeout=10)
        except Exception:
            check("missing_artifacts grounds against the git tree", True, "git absent — skipped")
            return
        miss = F.missing_artifacts(["real content", "gone/Thing.java"], str(r))
        check("missing_artifacts grounds against the git tree",
              miss == ["gone/Thing.java"], str(miss))


def t_new_staleness_candidates_reach_hook_output():
    """The two new detectors surface in the emitted context in the same style
    (and under the same budget) as the vanished-artifact line."""
    with tempfile.TemporaryDirectory() as t:
        r = Path(t)
        (r / "package.json").write_text(json.dumps({"dependencies": {"react": "18.2.0"}}))
        mig = r / "migrations"; mig.mkdir()
        (mig / "V27__init.sql").write_text("x")
        (mig / "V28__more.sql").write_text("x")
        (r / "CLAUDE.md").write_text(
            "# p\n\n## Architecture\nx.\n\nRun `npm test`.\n\n"
            "### Decisions & Learnings\n\n"
            "- 2026-01-01 — **ui** — pinned react 17.0; latest migration is `V27`.\n")
        proc = subprocess.run([sys.executable, str(HERE / "audit-claude-md.py")],
                              cwd=str(r), capture_output=True, text=True, timeout=20)
        ctx = ""
        try:
            ctx = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
        except Exception:
            pass
        check("a stale version pin reaches the emitted context",
              proc.returncode == 0 and "stale version pin" in ctx and "react" in ctx, ctx[:200])
        check("a stale sequence fact reaches the emitted context",
              "stale sequence fact" in ctx and "V27" in ctx, ctx[:200])


def t_hook_emits_valid_json_and_never_blocks():
    """The hook runs on SessionStart. Malformed stdout or a non-zero exit would
    degrade every session start, so both are asserted directly."""
    with tempfile.TemporaryDirectory() as t:
        r = repo(Path(t), "hooked", "# p\n\n## Architecture\nx.\n", ["pom.xml"])
        proc = subprocess.run([sys.executable, str(HERE / "audit-claude-md.py")],
                              cwd=str(r), capture_output=True, text=True, timeout=20)
        ok_json, ctx = False, ""
        try:
            ctx = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
            ok_json = True
        except Exception as exc:
            ctx = f"{exc}: {proc.stdout[:120]!r}"
        check("the hook exits 0 and emits parseable SessionStart JSON",
              proc.returncode == 0 and ok_json, f"rc={proc.returncode} {ctx[:120]}")
        check("the coverage gap reaches the emitted context",
              "Coverage" in ctx or "⬆️" in ctx, ctx[:160])


def t_silent_when_healthy():
    with tempfile.TemporaryDirectory() as t:
        r = repo(Path(t), "clean", FULL, ["pom.xml"])
        proc = subprocess.run([sys.executable, str(HERE / "audit-claude-md.py")],
                              cwd=str(r), capture_output=True, text=True, timeout=20)
        check("a healthy small CLAUDE.md produces no output at all",
              proc.returncode == 0 and proc.stdout.strip() == "",
              f"rc={proc.returncode} out={proc.stdout[:120]!r}")


def t_thresholds_are_per_repo_configurable():
    """"Concise" is not a universal number — 40 KB is bloat in a library and
    reasonable in a monorepo. The defaults were calibrated on one person's
    repos, so they have to be overridable or they are just that person's taste
    imposed on everyone."""
    with tempfile.TemporaryDirectory() as t:
        r = repo(Path(t), "cfg", FULL, ["pom.xml"])
        base = audit.load_config(str(r))
        check("with no config file, the defaults are used",
              base["file_warn_kb"] == audit.T_FILE_WARN_KB and base["coverage"] is True)

        cdir = r / ".claude" / "evolving-claude-md"
        cdir.mkdir(parents=True)
        (cdir / "config.json").write_text(json.dumps(
            {"file_warn_kb": 100, "entries_recommend": 500, "coverage": False}))
        got = audit.load_config(str(r))
        check("a repo config overrides only the keys it names",
              got["file_warn_kb"] == 100 and got["entries_recommend"] == 500
              and got["lines_warn"] == audit.T_LINES_WARN, str(got))
        check("unknown keys in a config are ignored, not merged in",
              set(got) == set(audit.DEFAULTS))

        (cdir / "config.json").write_text("{ this is not json")
        check("a corrupt config falls back to defaults instead of raising",
              audit.load_config(str(r))["file_warn_kb"] == audit.T_FILE_WARN_KB)


def t_coverage_can_be_switched_off():
    with tempfile.TemporaryDirectory() as t:
        r = repo(Path(t), "nocov", "# p\n\nnothing here.\n", ["pom.xml"])
        cdir = r / ".claude" / "evolving-claude-md"; cdir.mkdir(parents=True)
        (cdir / "config.json").write_text(json.dumps({"coverage": False}))
        proc = subprocess.run([sys.executable, str(HERE / "audit-claude-md.py")],
                              cwd=str(r), capture_output=True, text=True, timeout=20)
        check("coverage:false silences the upward check entirely",
              proc.returncode == 0 and "Coverage" not in proc.stdout and "⬆️" not in proc.stdout,
              proc.stdout[:140])


def t_companion_files_are_measured():
    """.claude.local.md and nested CLAUDE.md load into context exactly like the
    root file, so bloat in them is the same problem measured nowhere."""
    with tempfile.TemporaryDirectory() as t:
        r = repo(Path(t), "multi", FULL, ["pom.xml"])
        (r / "packages" / "api").mkdir(parents=True)
        (r / "packages" / "api" / "CLAUDE.md").write_text("x" * 40_000)
        (r / ".claude.local.md").write_text("y" * 40_000)
        (r / "node_modules" / "pkg").mkdir(parents=True)
        (r / "node_modules" / "pkg" / "CLAUDE.md").write_text("z" * 90_000)

        names = {n for n, _ in audit.companion_files(str(r))}
        check("finds .claude.local.md and nested CLAUDE.md",
              audit.LOCAL_MD in names and any("api" in n for n in names), str(names))
        check("never walks into node_modules / build output",
              not any("node_modules" in n for n in names), str(names))
        check("the root CLAUDE.md is not double-counted as a companion",
              "CLAUDE.md" not in names, str(names))

        proc = subprocess.run([sys.executable, str(HERE / "audit-claude-md.py")],
                              cwd=str(r), capture_output=True, text=True, timeout=20)
        check("an oversized companion file is reported",
              "Other context files" in proc.stdout, proc.stdout[:200])


def t_nested_can_be_switched_off():
    with tempfile.TemporaryDirectory() as t:
        r = repo(Path(t), "flatonly", FULL, ["pom.xml"])
        (r / ".claude.local.md").write_text("y" * 60_000)
        cdir = r / ".claude" / "evolving-claude-md"; cdir.mkdir(parents=True)
        (cdir / "config.json").write_text(json.dumps({"nested": False}))
        proc = subprocess.run([sys.executable, str(HERE / "audit-claude-md.py")],
                              cwd=str(r), capture_output=True, text=True, timeout=20)
        check("nested:false stops companion reporting",
              proc.returncode == 0 and "Other context files" not in proc.stdout,
              proc.stdout[:140])


# --- capture-side checks (issue #37 / #39 / #41) --------------------------
# The pinned cases from the issue, plus drift. Negative cases carry equal
# weight: every one of these injects into SessionStart context when it fires.

def _git(r: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(r), *args], capture_output=True, timeout=10)


def git_repo(tmp: Path, name: str, claude_md: str, commits: int = 1,
             tracked: dict[str, str] | None = None) -> Path:
    r = repo(tmp, name, claude_md)
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    for rel, content in (tracked or {}).items():
        p = r / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "seed")
    for i in range(commits - 1):
        _git(r, "commit", "-q", "--allow-empty", "-m", f"c{i}")
    return r


def t_adoption_fires_on_handrolled_log():
    txt = ("# proj\n\n## Hard-won gotchas\n\n"
           "- find is bfs here\n- mtime is worthless\n- extension != codec\n")
    got = audit.adoption_candidate(txt, 0)
    check("hand-rolled gotchas + 0 D&L entries → adoption fires",
          got is not None and "UNADOPTED" in got, str(got))


def t_adoption_silent_when_log_healthy():
    txt = "# proj\n\n## Hard-won gotchas\n\n- a\n- b\n- c\n"
    check("adoption silent when D&L entries exist",
          audit.adoption_candidate(txt, 6) is None)
    check("adoption silent when the heading has <3 bullets",
          audit.adoption_candidate("# p\n\n## Learnings\n\n- only one\n", 0) is None)
    check("adoption silent on a plain file",
          audit.adoption_candidate(FULL, 0) is None)


def t_empty_log_needs_all_three_signals():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        young = git_repo(tmp, "young", "# p\n", commits=3)
        check("a 3-commit new repo is never called an empty log",
              audit.empty_log_signal("# p\n", 0, str(young)) is None)
        docs = {f"docs/f{i}.md": "x" * 4000 for i in range(10)}
        old = git_repo(tmp, "old", "# p\n", commits=25, tracked=docs)
        got = audit.empty_log_signal("# p\n", 0, str(old))
        check("25 commits + heavy docs/ + no entries → empty-log fires",
              got is not None and "EMPTY LOG" in got, str(got))
        check("empty-log silent once entries exist",
              audit.empty_log_signal("# p\n", 5, str(old)) is None)


def t_recurrence_matches_time_not_file():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        r = git_repo(tmp, "recur", "# p\n", tracked={
            "docs/a.md": "This is the third time a heuristic pointed the wrong way.",
            "docs/b.md": "Open the third file in the list.",
        })
        got = audit.docs_recurrences(str(r))
        check("'the third time' in docs fires recurrence",
              got == ["docs/a.md"], str(got))
        r2 = git_repo(tmp, "norec", "# p\n", tracked={
            "docs/b.md": "Open the third file in the list."})
        check("'the third file' stays silent",
              audit.docs_recurrences(str(r2)) == [])


def t_layout_drift_both_directions():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        tracked = {f"engine/f{i}.py": "x" for i in range(4)}
        tracked.update({"docs/readme.md": "x"})
        r = git_repo(tmp, "drift", "# p\nsee `plugins/` for code\n", tracked=tracked)
        new, gone = audit.layout_drift((r / "CLAUDE.md").read_text(), str(r))
        check("a tracked, unmentioned top-level dir fires drift",
              new == ["engine"], str(new))
        check("conventional dirs (docs) are exempt from drift",
              "docs" not in new)
        r2 = git_repo(tmp, "ok", "# p\nthe engine/ dir holds the core\n", tracked=tracked)
        new2, _ = audit.layout_drift((r2 / "CLAUDE.md").read_text(), str(r2))
        check("mentioning the dir clears drift", new2 == [], str(new2))
        # stale-layout: `engine/` had history, then vanished
        _git(r, "rm", "-rq", "engine")
        _git(r, "commit", "-qm", "drop engine")
        _, gone3 = audit.layout_drift("# p\nsee `engine/` for the core\n", str(r))
        check("a mentioned dir gone from the tree (with history) is stale layout",
              gone3 == ["engine/"], str(gone3))
        _, gone4 = audit.layout_drift("# p\ndecks land under `presentation/`\n", str(r))
        check("a foreign path with no git history here stays silent",
              gone4 == [], str(gone4))


def t_drift_respects_min_files_and_skip():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        r = git_repo(tmp, "small", "# p\n", tracked={"scratch/one.txt": "x"})
        new, _ = audit.layout_drift((r / "CLAUDE.md").read_text(), str(r))
        check("a dir under drift_min_files stays silent", new == [], str(new))
        r2 = git_repo(tmp, "skip", "# p\n<!-- audit-skip: layout-drift -->\n",
                      tracked={f"engine/f{i}.py": "x" for i in range(4)})
        new2, gone2 = audit.layout_drift((r2 / "CLAUDE.md").read_text(), str(r2),
                                         skipped={"layout-drift"})
        check("audit-skip: layout-drift opts out", new2 == [] and gone2 == [])


def t_capture_triggers_are_default_off():
    with tempfile.TemporaryDirectory() as t:
        r = git_repo(Path(t), "cap", "# p\n")
        payload = json.dumps({"tool_input": {"command": "git commit -m x"}})
        proc = subprocess.run(
            [sys.executable, str(HERE / "capture-triggers.py"), "commit"],
            input=payload, cwd=str(r), capture_output=True, text=True, timeout=10)
        check("commit mining is silent by default",
              proc.returncode == 0 and proc.stdout.strip() == "", proc.stdout[:120])


def t_commit_mining_fires_on_gotcha_language():
    with tempfile.TemporaryDirectory() as t:
        r = git_repo(Path(t), "mine", "# p\n")
        _git(r, "commit", "-q", "--allow-empty", "-m",
             "fix: turns out the API silently reports success")
        cdir = r / ".claude" / "evolving-claude-md"; cdir.mkdir(parents=True)
        (cdir / "config.json").write_text(json.dumps({"commit_mining": True}))
        payload = json.dumps({"tool_input": {"command": "git commit -m x"}})
        proc = subprocess.run(
            [sys.executable, str(HERE / "capture-triggers.py"), "commit"],
            input=payload, cwd=str(r), capture_output=True, text=True, timeout=10)
        check("gotcha-shaped commit message fires the promotion nudge",
              "gotcha-shaped" in proc.stdout and "learn-on-failure" in proc.stdout,
              proc.stdout[:160])
        _git(r, "commit", "-q", "--allow-empty", "-m", "chore: bump version")
        proc2 = subprocess.run(
            [sys.executable, str(HERE / "capture-triggers.py"), "commit"],
            input=payload, cwd=str(r), capture_output=True, text=True, timeout=10)
        check("a routine commit message stays silent",
              proc2.stdout.strip() == "", proc2.stdout[:120])


def t_session_end_capture_fires_once():
    with tempfile.TemporaryDirectory() as t:
        r = git_repo(Path(t), "stopcap", "# p\n")
        cdir = r / ".claude" / "evolving-claude-md"; cdir.mkdir(parents=True)
        (cdir / "config.json").write_text(json.dumps({"capture_prompt": "session-end"}))
        transcript = r / "t.jsonl"
        transcript.write_text(
            '{"name": "Bash", "input": {"command": "git commit -m x"}}\n'
            '{"name": "Edit", "file_path": "src/a.py"}\n')
        payload = json.dumps({"session_id": "s1", "transcript_path": str(transcript)})
        run = lambda: subprocess.run(
            [sys.executable, str(HERE / "capture-triggers.py"), "stop"],
            input=payload, cwd=str(r), capture_output=True, text=True, timeout=10)
        p1 = run()
        check("session with commits but no CLAUDE.md touch blocks stop once",
              '"decision": "block"' in p1.stdout and "0-3" in p1.stdout, p1.stdout[:160])
        p2 = run()
        check("the second stop in the same session is silent",
              p2.stdout.strip() == "", p2.stdout[:120])
        t2 = r / "t2.jsonl"
        t2.write_text(
            '{"name": "Bash", "input": {"command": "git commit -m x"}}\n'
            '{"name": "Edit", "file_path": "CLAUDE.md"}\n')
        p3 = subprocess.run(
            [sys.executable, str(HERE / "capture-triggers.py"), "stop"],
            input=json.dumps({"session_id": "s2", "transcript_path": str(t2)}),
            cwd=str(r), capture_output=True, text=True, timeout=10)
        check("a session that DID touch CLAUDE.md is never prompted",
              p3.stdout.strip() == "", p3.stdout[:120])


CHECKS = [
    t_command_gap_is_grounded_in_the_build_file,
    t_command_gap_clears_when_mentioned,
    t_every_build_system_is_detectable,
    t_layout_gap_needs_a_complex_tree,
    t_build_output_dirs_dont_count_as_layout,
    t_audit_skip_opts_out,
    t_a_good_claude_md_is_silent,
    t_no_regression_on_real_repos,
    t_version_pin_is_grounded_in_the_build_file,
    t_version_pin_stays_silent_when_uncertain,
    t_sequence_fact_is_grounded_in_the_tree,
    t_sequence_fact_stays_silent_when_uncertain,
    t_vanished_artifact_predicate_moved_to_freshness,
    t_new_staleness_candidates_reach_hook_output,
    t_hook_emits_valid_json_and_never_blocks,
    t_silent_when_healthy,
    t_thresholds_are_per_repo_configurable,
    t_coverage_can_be_switched_off,
    t_companion_files_are_measured,
    t_nested_can_be_switched_off,
    t_adoption_fires_on_handrolled_log,
    t_adoption_silent_when_log_healthy,
    t_empty_log_needs_all_three_signals,
    t_recurrence_matches_time_not_file,
    t_layout_drift_both_directions,
    t_drift_respects_min_files_and_skip,
    t_capture_triggers_are_default_off,
    t_commit_mining_fires_on_gotcha_language,
    t_session_end_capture_fires_once,
]


def main() -> int:
    print("\n  evolving-claude-md harness\n")
    for fn in CHECKS:
        try:
            fn()
        except Exception as exc:
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
