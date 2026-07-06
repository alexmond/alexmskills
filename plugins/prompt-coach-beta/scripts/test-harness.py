#!/usr/bin/env python3
"""prompt-coach-beta — release test harness.

Run after every release to confirm the plugin's live behaviors still work.
Self-contained: spins up throwaway HOME + repo dirs per check, drives the
UserPromptSubmit hook (analyze-prompt.py) and the config surface (config.py)
as real subprocesses, and asserts on their output.

    python3 scripts/test-harness.py           # run all, human summary
    python3 scripts/test-harness.py --json     # machine-readable
    echo $?                                    # 0 = all pass, 1 = failure(s)

No external deps. Mocks `webbrowser` (via PYTHONPATH) for --open checks so
nothing actually launches a browser.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANALYZER = HERE / "analyze-prompt.py"
CONFIG = HERE / "config.py"
REPO_ROOT = HERE.parent.parent.parent  # …/alexmskills

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))


# ── harness plumbing ────────────────────────────────────────────────────────

def _fresh() -> tuple[Path, Path]:
    """A throwaway HOME + repo cwd, each with .claude/prompt-coach/."""
    home = Path(tempfile.mkdtemp())
    cwd = Path(tempfile.mkdtemp())
    (home / ".claude/prompt-coach").mkdir(parents=True)
    (cwd / ".claude/prompt-coach").mkdir(parents=True)
    return home, cwd


def _hook(cwd: Path, home: Path, prompt: str) -> str:
    """Drive the UserPromptSubmit hook; return additionalContext (or '')."""
    env = dict(os.environ)
    env["HOME"] = str(home)
    r = subprocess.run(
        [sys.executable, str(ANALYZER)],
        input=json.dumps({"cwd": str(cwd), "prompt": prompt}),
        capture_output=True, text=True, env=env,
    )
    if r.stdout.strip().startswith("{"):
        try:
            return r.stdout, json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        except Exception:
            return r.stdout, ""
    return r.stdout, ""


def _cfg(cwd: Path, home: Path, *args: str, mock_browser: bool = False):
    env = dict(os.environ)
    env["HOME"] = str(home)
    if mock_browser:
        mock = Path(tempfile.mkdtemp())
        (mock / "webbrowser.py").write_text(
            "import sys\ndef open(u,*a,**k):\n"
            " sys.stderr.write('WB:'+u+chr(10)); return True\n")
        env["PYTHONPATH"] = str(mock)
    return subprocess.run(
        [sys.executable, str(CONFIG), "--cwd", str(cwd), *args],
        capture_output=True, text=True, env=env,
    )


# ── checks ──────────────────────────────────────────────────────────────────

def t_hook_clean_ack():
    h, c = _fresh()
    _, ctx = _hook(c, h, "In src/auth/login.py, make handleLogin reject empty "
                          "passwords with a 422; keep tests green.")
    check("clean prompt → ✓ ack",
          "✓ prompt-coach · clean prompt" in ctx, ctx[:120])


def t_hook_collaborator_block_with_urls():
    h, c = _fresh()
    _, ctx = _hook(c, h, "fix it fast")
    ok = ("collaborator mode" in ctx and "https://platform.claude.com" in ctx)
    check("rule-firing prompt → collaborator block w/ clickable URL", ok, ctx[:120])


def t_show_source_urls_off():
    h, c = _fresh()
    (h / ".claude/prompt-coach/config.json").write_text(
        json.dumps({"show_source_urls": False}))
    _, ctx = _hook(c, h, "fix it fast")
    check("show_source_urls=false → slug only, no URL",
          "https://" not in ctx and "be-clear-and-direct" in ctx, ctx[:120])


def t_enabled_false_silent():
    h, c = _fresh()
    (h / ".claude/prompt-coach/config.json").write_text(json.dumps({"enabled": False}))
    raw, ctx = _hook(c, h, "fix it fast")
    check("enabled=false → fully silent", not ctx and not raw.strip(), raw[:80])


def t_no_double_count():
    h, c = _fresh()
    _hook(c, h, "fix it fast")
    st = json.loads((h / ".claude/prompt-coach/state.json").read_text())
    ft = st.get("rules", {}).get("vague-reference", {}).get("fires_total", 0)
    check("fires_total increments by exactly 1 (no double-count)", ft == 1,
          f"fires_total={ft}")


def t_mastery_congrats():
    h, c = _fresh()
    sp = h / ".claude/prompt-coach/state.json"
    _hook(c, h, "hello there friend")
    st = json.loads(sp.read_text())
    # v0.40 — mastery is demonstration-driven: seed 2 demonstrations + a
    # clean streak past the regression guard, then send a prompt that
    # DEMONSTRATES scoped reference (names a file/function) so the mirroring
    # positive fires → demonstrations hits 3 → vague-reference masters.
    st.setdefault("rules", {})["vague-reference"] = {
        "status": "practicing", "fires_total": 1, "clean_streak": 5,
        "demonstrations": 2, "last_fired_at": None, "last_nudged_at": None,
        "graduated_at": None}
    sp.write_text(json.dumps(st))
    _, ctx = _hook(c, h, "In src/db/pool.py, cap the connection pool at 20; "
                         "keep the existing retry logic untouched.")
    check("mastery event → 🎓 congrats renders inline",
          "🎓 prompt-coach — " in ctx and "mastered" in ctx.lower(), ctx[:120])


def t_earned_mastery_demonstration_driven():
    """v0.40 — the core fix: mastery comes from DEMONSTRATIONS (using the
    technique), not from clean prompts that never exercise the rule.
    (a) A demonstrating clean prompt increments `demonstrations`.
    (b) Clean-but-non-demonstrating prompts do NOT march a rule to mastery —
        the old absence-driven bug."""
    h, c = _fresh()
    sp = h / ".claude/prompt-coach/state.json"
    _hook(c, h, "hello there friend")
    # (a) a prompt that names a file demonstrates scoped reference
    _hook(c, h, "In src/api/routes.py, add a health check endpoint returning 200; "
                "leave the existing routes untouched.")
    st = json.loads(sp.read_text())
    demos = int(st.get("rules", {}).get("vague-reference", {}).get("demonstrations", 0))
    # (b) many clean-but-empty prompts must NOT master vague-reference
    for _ in range(20):
        _hook(c, h, "hello there friend")
    st2 = json.loads(sp.read_text())
    status = st2.get("rules", {}).get("vague-reference", {}).get("status", "practicing")
    check("earned mastery: demonstrations count + no mastery-by-absence",
          demos >= 1 and status != "mastered",
          f"demos_after_demo={demos} status_after_20_empty={status}")


def t_picker_skip():
    """A prompt that looks like a picker answer should be skipped when the
    prior assistant turn was a real picker. We simulate by writing a
    transcript the analyzer reads. Simplest proxy: a bare conversational
    answer is skipped as conversational."""
    h, c = _fresh()
    raw, ctx = _hook(c, h, "yes")
    st = json.loads((h / ".claude/prompt-coach/state.json").read_text())
    # 'yes' is conversational → skipped, no collaborator block
    check("conversational 'yes' → skipped (no coach block)",
          "collaborator mode" not in ctx, ctx[:80])


def t_config_roundtrip():
    h, c = _fresh()
    r = _cfg(c, h, "get", "show_source_urls")
    ok_get = "True" in r.stdout
    _cfg(c, h, "--scope", "global", "set", "show_source_urls", "false")
    r2 = _cfg(c, h, "get", "show_source_urls")
    ok_set = "False" in r2.stdout
    r3 = _cfg(c, h, "describe", "show_source_urls")
    ok_desc = "clickable" in r3.stdout.lower()
    check("config get/set/describe roundtrip", ok_get and ok_set and ok_desc,
          f"get={ok_get} set={ok_set} desc={ok_desc}")


def t_mastery_reset_zeros_demonstrations():
    """v0.40.1 — mastery-reset must zero `demonstrations` (the mastery
    driver) and drop the `mastery_basis` tag; otherwise a
    demonstration-earned rule would instantly re-master after a reset."""
    h, c = _fresh()
    sp = h / ".claude/prompt-coach/state.json"
    sp.write_text(json.dumps({"rules": {"no-verify-loop": {
        "status": "mastered", "fires_total": 2, "clean_streak": 9,
        "demonstrations": 5, "mastery_basis": "demonstrated"}}}))
    _cfg(c, h, "mastery-reset", "no-verify-loop")
    rs = json.loads(sp.read_text()).get("rules", {}).get("no-verify-loop", {})
    check("mastery-reset zeros demonstrations + drops mastery_basis",
          rs.get("demonstrations") == 0 and rs.get("status") == "practicing"
          and "mastery_basis" not in rs,
          f"demos={rs.get('demonstrations')} status={rs.get('status')} "
          f"basis_present={'mastery_basis' in rs}")


def t_analyze_single():
    h, c = _fresh()
    r = _cfg(c, h, "--json", "analyze", "fix it and make it better and faster")
    try:
        d = json.loads(r.stdout)
        ok = d["mode"] == "single" and len(d["fired"]) >= 3 and d["fired"][0].get("url")
    except Exception:
        ok = False
    check("analyze <text> → full-catalog fired[] with URLs", ok, r.stdout[:100])


def t_analyze_history():
    h, c = _fresh()
    # seed a log
    log = c / ".claude/prompt-coach/log.md"
    log.write_text(
        "- [t] fired=[—] outcome=collaborator:candidates=1 prompt=«fix it»\n"
        "- [t] fired=[—] outcome=ack:clean prompt=«In src/x.py cap pool at 20»\n")
    r = _cfg(c, h, "--json", "analyze", "--last", "5")
    try:
        d = json.loads(r.stdout)
        ok = d["mode"] == "history" and d["n"] == 2 and "rule_frequency" in d
    except Exception:
        ok = False
    check("analyze --last N → history report", ok, r.stdout[:100])


def t_sources_open():
    h, c = _fresh()
    r = _cfg(c, h, "sources", "vague-reference", "--open", mock_browser=True)
    check("sources <rule> --open → launches doc URL(s)",
          any("WB:" in l and "be-clear-and-direct" in l
              for l in r.stderr.splitlines()), r.stderr[:120])


def t_paths():
    h, c = _fresh()
    r = _cfg(c, h, "paths")
    ok = ("SKILL.md" in r.stdout and "Runnable scripts" in r.stdout
          and "config.py" in r.stdout)
    check("paths → folders + runnable scripts", ok, r.stdout[:80])
    r2 = _cfg(c, h, "paths", "--open", mock_browser=True)
    check("paths --open → launches folder/docs",
          any("WB:file://" in l for l in r2.stderr.splitlines()), r2.stderr[:80])


def t_scripts_parse():
    import ast
    ok = True
    detail = ""
    for p in (ANALYZER, CONFIG):
        try:
            ast.parse(p.read_text())
        except SyntaxError as e:
            ok = False
            detail = f"{p.name}: {e}"
    check("both scripts parse", ok, detail)


def t_incremental_routing_rule():
    """incremental-routing (L5, v0.39) — fires on terse per-step routing,
    stays quiet when a batching mechanism is named or the prompt is a bare
    conversational continuation. L5 isn't active in a fresh hook run, so this
    is a unit-level check against the analyzer module directly."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_an", ANALYZER)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_an"] = m
    spec.loader.exec_module(m)
    registered = any(r.id == "incremental-routing" for r in m.RULES)
    fn = getattr(m, "rule_incremental_routing", None)
    fires = fn and fn("continue one after another") and \
        not m.is_conversational("continue one after another")
    quiet = fn and not fn("do these as a task list") and \
        not fn("run all of them in parallel")
    conv_skip = m.is_conversational("continue")  # bare continue short-circuits
    check("incremental-routing rule fires on per-step routing, quiet when batched",
          bool(registered and fires and quiet and conv_skip),
          f"registered={registered} fires={bool(fires)} quiet={bool(quiet)}")


def t_grandfather_migration():
    """v0.40 — existing masteries are grandfathered, not wiped: a pre-v0.40
    mastered rule (no demonstrations, no mastery_basis) stays mastered, gets
    demonstrations backfilled to 0 and tagged mastery_basis=legacy."""
    h, c = _fresh()
    sp = h / ".claude/prompt-coach/state.json"
    _hook(c, h, "hello there friend")
    st = json.loads(sp.read_text())
    st.setdefault("rules", {})["unbounded-scope"] = {
        "status": "mastered", "fires_total": 0, "clean_streak": 56}
    st.pop("v40_migration_done", None)
    sp.write_text(json.dumps(st))
    _hook(c, h, "hello there friend")
    rs = json.loads(sp.read_text()).get("rules", {}).get("unbounded-scope", {})
    check("v40 grandfather: legacy mastery kept + tagged, not wiped",
          rs.get("status") == "mastered" and rs.get("mastery_basis") == "legacy"
          and "demonstrations" in rs,
          f"status={rs.get('status')} basis={rs.get('mastery_basis')}")


def t_marketplace_valid():
    r = subprocess.run(["make", "-C", str(REPO_ROOT), "validate"],
                       capture_output=True, text=True)
    check("marketplace validates", "Marketplace valid" in r.stdout,
          r.stdout[-100:])


CHECKS = [
    t_scripts_parse,
    t_hook_clean_ack,
    t_hook_collaborator_block_with_urls,
    t_show_source_urls_off,
    t_enabled_false_silent,
    t_no_double_count,
    t_mastery_congrats,
    t_picker_skip,
    t_config_roundtrip,
    t_mastery_reset_zeros_demonstrations,
    t_analyze_single,
    t_analyze_history,
    t_sources_open,
    t_paths,
    t_incremental_routing_rule,
    t_earned_mastery_demonstration_driven,
    t_grandfather_migration,
    t_marketplace_valid,
]


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    for fn in CHECKS:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — a crashing check is a failure
            check(fn.__name__, False, f"raised {type(exc).__name__}: {exc}")

    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)

    if as_json:
        print(json.dumps({
            "passed": passed, "total": total,
            "results": [{"name": n, "ok": ok, "detail": d}
                        for n, ok, d in _results],
        }, indent=2))
    else:
        print(f"\nprompt-coach-beta test harness — {passed}/{total} passed\n")
        for name, ok, detail in _results:
            mark = "✓" if ok else "✗"
            line = f"  {mark} {name}"
            if not ok and detail:
                line += f"\n      → {detail}"
            print(line)
        print()
        if passed == total:
            print("  ALL GREEN")
        else:
            print(f"  {total - passed} FAILURE(S)")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
