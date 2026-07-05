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
    st.setdefault("rules", {})["vague-reference"] = {
        "status": "practicing", "fires_total": 1, "clean_streak": 14,
        "last_fired_at": None, "last_nudged_at": None, "graduated_at": None}
    sp.write_text(json.dumps(st))
    _, ctx = _hook(c, h, "In src/db/pool.py, cap the connection pool at 20; "
                         "keep the existing retry logic untouched.")
    check("mastery event → 🎓 congrats renders inline",
          "🎓 prompt-coach — " in ctx and "mastered" in ctx.lower(), ctx[:120])


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
    t_analyze_single,
    t_analyze_history,
    t_sources_open,
    t_paths,
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
