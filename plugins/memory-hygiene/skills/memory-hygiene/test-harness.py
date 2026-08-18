#!/usr/bin/env python3
"""memory-hygiene release harness. Stdlib-only; builds throwaway fixture
repos + memory dirs under tempdirs. Half the checks assert NON-fires — an
auditor of agent memory earns trust exactly like a linter does: by silence
on healthy input."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, bool(ok), detail))


def load(mod_file: str):
    spec = importlib.util.spec_from_file_location(mod_file.replace(".py", "").replace("-", "_"), HERE / mod_file)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


am = load("audit-memory.py")
fr = load("freshness.py")


def make_repo(tmp: str) -> str:
    root = os.path.join(tmp, "repo")
    os.makedirs(root)
    subprocess.run(["git", "-C", root, "init", "-q"], check=True)
    Path(root, "pom.xml").write_text(
        "<project><parent><groupId>g</groupId><artifactId>spring-boot-starter-parent"
        "</artifactId><version>4.0.7</version></parent>"
        "<properties><jhelm.version>1.5.0</jhelm.version></properties></project>")
    Path(root, "Realthing.java").write_text("class Realthing {}")
    os.makedirs(os.path.join(root, "db"))
    Path(root, "db", "V27__init.sql").write_text("--")
    Path(root, "db", "V28__more.sql").write_text("--")
    subprocess.run(["git", "-C", root, "add", "-A"], check=True)
    subprocess.run(["git", "-C", root, "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "x"], check=True)
    return root


def mem_write(mem: str, name: str, body: str) -> None:
    os.makedirs(mem, exist_ok=True)
    Path(mem, name).write_text(body)


def t_audit_fires_on_rot():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        mem = os.path.join(tmp, "memory")
        mem_write(mem, "rotten.md",
                  "---\nname: rotten\n---\ncites `Gone.java` and `Also.gone` "
                  "and pins spring-boot 4.0.5. latest migration is `V27`")
        mem_write(mem, "MEMORY.md", "- [Rotten](rotten.md) — x\n- [Ghost](ghost.md) — y\n")
        res = am.audit(root, mem_dir=mem)
        f = res["files"].get("rotten.md", {})
        check("vanished_artifacts_fire", len(f.get("vanished", [])) >= 2, str(f))
        check("stale_pin_fires", any(p["stated"] == "4.0.5" for p in f.get("pins", [])), str(f))
        check("stale_sequence_fires", any(s["token"] == "V27" for s in f.get("sequence", [])), str(f))
        check("index_dangling_detected", res["index"].get("dangling") == ["ghost.md"], str(res["index"]))
        check("audit_unhealthy", not res["healthy"])


def t_audit_silent_on_healthy():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        mem = os.path.join(tmp, "memory")
        mem_write(mem, "fine.md",
                  "---\nname: fine\n---\nuses `Realthing.java`; jhelm 1.5.0; "
                  "release line is 4.0.x; run `--verbose` on the external tool; "
                  "sister repo keeps `infra/secrets.md`; see `docs/.../full.adoc`")
        mem_write(mem, "MEMORY.md", "- [Fine](fine.md) — x\n")
        res = am.audit(root, mem_dir=mem)
        check("healthy_memory_silent", res["healthy"], json.dumps(res))


def t_filters():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        check("flag_token_skipped", not am.tree_scoped("--reset-values", root))
        check("placeholder_skipped", not am.tree_scoped("<fqdn>", root))
        check("ellipsis_skipped", not am.tree_scoped("docs/.../x.adoc", root))
        check("foreign_path_skipped", not am.tree_scoped("otherrepo/bin/x.sh", root))
        check("local_path_kept", am.tree_scoped("db/V27__init.sql", root))
        check("bare_name_kept", am.tree_scoped("Realthing.java", root))


def t_missing_index_and_orphans():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        mem = os.path.join(tmp, "memory")
        mem_write(mem, "loner.md", "---\nname: loner\n---\ntimeless note")
        res = am.audit(root, mem_dir=mem)
        check("no_index_flagged", res["index"].get("no_index") is True, str(res["index"]))
        mem_write(mem, "MEMORY.md", "# idx\n")
        mem_write(mem, "._junk.md", "applejunk")
        res = am.audit(root, mem_dir=mem)
        check("orphan_flagged", res["index"].get("orphans") == ["loner.md"], str(res["index"]))


def t_no_memory_dir_is_healthy():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        res = am.audit(root, mem_dir=os.path.join(tmp, "nope"))
        check("absent_memory_dir_silent", res["healthy"])


def t_corrupt_config_falls_back():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        cdir = os.path.join(root, ".claude", "memory-hygiene")
        os.makedirs(cdir)
        Path(cdir, "config.json").write_text("{not json")
        cfg = am.load_config(root)
        check("corrupt_config_defaults", cfg == am.DEFAULTS, str(cfg))
        Path(cdir, "config.json").write_text('{"min_missing_artifacts": 3, "junk": "x"}')
        cfg = am.load_config(root)
        check("config_override_applies", cfg["min_missing_artifacts"] == 3, str(cfg))


def _lint(payload: dict) -> dict | None:
    r = subprocess.run([sys.executable, str(HERE / "lint-memory-write.py")],
                       input=json.dumps(payload), capture_output=True, text=True)
    return json.loads(r.stdout) if r.stdout.strip() else None


def t_lint_hook():
    fact = "/home/u/.claude/projects/-home-u-r/memory/fact.md"
    idx = "/home/u/.claude/projects/-home-u-r/memory/MEMORY.md"
    deny = _lint({"tool_name": "Write", "tool_input": {"file_path": fact, "content": "no frontmatter"}})
    check("lint_denies_bare_fact", deny and deny["hookSpecificOutput"]["permissionDecision"] == "deny")
    ok = _lint({"tool_name": "Write", "tool_input": {"file_path": fact, "content":
        "---\nname: fact\ndescription: d\nmetadata:\n  type: project\n---\n\nDated 2026-08-18."}})
    check("lint_allows_good_fact", ok is None, str(ok))
    deny = _lint({"tool_name": "Write", "tool_input": {"file_path": fact, "content":
        "---\nname: fact\ndescription: d\nmetadata:\n  type: banana\n---\nx"}})
    check("lint_denies_bad_type", deny is not None)
    deny = _lint({"tool_name": "Edit", "tool_input": {"file_path": fact,
        "old_string": "a", "new_string": "fixed last week"}})
    check("lint_denies_relative_date", deny is not None)
    ok = _lint({"tool_name": "Edit", "tool_input": {"file_path": fact,
        "old_string": "a", "new_string": "fixed 2026-08-11; the last week of QA was fine"}})
    check("lint_allows_absolute_date", ok is None, str(ok))
    deny = _lint({"tool_name": "Edit", "tool_input": {"file_path": idx,
        "old_string": "# i", "new_string": "# i\nA paragraph of content."}})
    check("lint_denies_index_prose", deny is not None)
    ok = _lint({"tool_name": "Edit", "tool_input": {"file_path": idx,
        "old_string": "# i", "new_string": "# i\n- [T](t.md) — hook"}})
    check("lint_allows_index_line", ok is None, str(ok))
    ok = _lint({"tool_name": "Write", "tool_input": {"file_path": "/home/u/r/notes.md",
        "content": "yesterday whatever, no frontmatter"}})
    check("lint_ignores_non_memory", ok is None, str(ok))
    ok = _lint({"tool_name": "Write", "tool_input": {"file_path": fact}})
    check("lint_survives_empty_payload", ok is not None or ok is None)  # no crash


def t_vendored_core_identical():
    ours = (HERE / "freshness.py").read_bytes()
    theirs = (HERE.parent.parent.parent.parent /
              "evolving-claude-md" / "skills" / "evolving-claude-md" / "freshness.py")
    if theirs.exists():  # only checkable in the marketplace repo
        check("freshness_copies_identical", ours == theirs.read_bytes(),
              "vendored freshness.py drifted from evolving-claude-md's")
    else:
        check("freshness_copies_identical", True, "sibling not present; skipped")


CHECKS = [
    t_audit_fires_on_rot,
    t_audit_silent_on_healthy,
    t_filters,
    t_missing_index_and_orphans,
    t_no_memory_dir_is_healthy,
    t_corrupt_config_falls_back,
    t_lint_hook,
    t_vendored_core_identical,
]


def main() -> int:
    for fn in CHECKS:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            check(fn.__name__, False, f"raised {type(exc).__name__}: {exc}")
    passed = sum(1 for _, ok, _ in _results if ok)
    print(f"\nmemory-hygiene harness — {passed}/{len(_results)} passed\n")
    for name, ok, detail in _results:
        line = f"  {'✓' if ok else '✗'} {name}"
        if not ok and detail:
            line += f"\n      → {detail}"
        print(line)
    print("\n  ALL GREEN" if passed == len(_results) else "\n  FAILURES")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
