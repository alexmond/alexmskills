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
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
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


def t_ack_is_informative():
    """v0.41.1 — the ack NAMES the rule (what you satisfied / what's watched)
    instead of a bare count like 'watching 1 rule'."""
    h, c = _fresh()
    # A clean, non-demonstrating prompt → 'watching for: <rule>' (named).
    _, ctx = _hook(c, h, "what can we do based on the sources")
    informative = ("watching for:" in ctx or "you used " in ctx
                   or "closest to mastery:" in ctx)
    bare_count = bool(re.search(r"watching \d+ rule", ctx))
    check("ack names the rule (no bare 'watching N rules')",
          informative and not bare_count, ctx.split("clean prompt")[-1][:80])


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


def t_collaborator_gate_configurable():
    """collaborator_gate (v0.43) — default false renders an HONEST 'proceeding'
    block that names which prompt it used and does NOT pretend to wait; true
    renders a real gate that STOPS. Both must state the '▸ Working from' prompt
    (the always-on clarity fix). Template must format without KeyError."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_an5", ANALYZER)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_an5"] = m
    spec.loader.exec_module(m)
    default_off = m.DEFAULT_CONFIG.get("collaborator_gate") is False
    honest = m._v34_context_for_claude("fix it", ["vague-reference"], gate=False)
    gated = m._v34_context_for_claude("fix it", ["vague-reference"], gate=True)
    honest_ok = ("Proceeding with this rewrite" in honest
                 and "Do NOT wait for confirmation" in honest
                 and "I'll wait" not in honest
                 and "▸ Working from" in honest)
    gated_ok = ("real gate" in gated and "STOP" in gated
                and "I'll wait" in gated
                and "Proceeding with this rewrite now" not in gated
                and "▸ Working from" in gated)
    check("collaborator_gate: default honest+names-prompt, gate=true stops+waits",
          bool(default_off and honest_ok and gated_ok),
          f"default_off={default_off} honest_ok={honest_ok} gated_ok={gated_ok}")


def t_rule_help_covers_all():
    """RULE_HELP (v0.44) — every shipped rule has human-facing help: a plain
    'catches' line + a bad and good example. A new rule can't ship without it.
    Also asserts build_dashboard surfaces those fields."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_an6", ANALYZER)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_an6"] = m
    spec.loader.exec_module(m)
    help_ = getattr(m, "RULE_HELP", {})
    missing = []
    for r in m.RULES:
        h = help_.get(r.id)
        if not h or not h.get("catches") or not h.get("bad") or not h.get("good"):
            missing.append(r.id)
    check("RULE_HELP covers all rules with catches + bad + good examples",
          not missing, f"missing/incomplete: {missing[:6]}")


def t_rules_doc_in_sync():
    """gen-rules-doc.py (v0.44.1) — the Antora per-rule reference is generated
    from build_dashboard, one entry per rule, each with an example + a Refs
    line. Also asserts the shipped .adoc is regenerated (no drift): its block
    between the markers must equal a fresh render."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_gen", HERE / "gen-rules-doc.py")
    gen = importlib.util.module_from_spec(spec)
    sys.modules["_gen"] = gen
    spec.loader.exec_module(gen)
    cfg = gen._load_config()
    fragment = gen.render(cfg.build_dashboard(Path("/tmp")))
    n_rules = len(cfg.RULES)
    ok_shape = (fragment.count("::") == n_rules
                and fragment.count("_Refs:_") == n_rules
                and "✗ `" in fragment and "✓ `" in fragment)
    check(f"gen-rules-doc renders all {n_rules} rules with example + Refs",
          ok_shape, f"::={fragment.count('::')} refs={fragment.count('_Refs:_')}")
    adoc = gen.ADOC.read_text() if gen.ADOC.exists() else ""
    data = cfg.build_dashboard(Path("/tmp"))
    summary = gen.render_summary(data)
    config = gen.render_config(data)
    # summary reports the real counts; config table has one row per schema key.
    n_cfg = len(data.get("config", []))
    summ_ok = f"**{n_rules} rules**" in summary and f"**{n_cfg} configuration keys**" in summary
    cfg_ok = config.count("| `") >= n_cfg   # one row per key (+ header cells)
    check(f"gen-rules-doc summary+config render real counts ({n_rules} rules, {n_cfg} keys)",
          bool(summ_ok and cfg_ok),
          f"summary_ok={summ_ok} config_rows_ok={cfg_ok}")
    in_sync = (gen.BEGIN in adoc and fragment.strip() in adoc
               and summary.strip() in adoc and config.strip() in adoc)
    check("shipped prompt-coach-beta.adoc is in sync (run gen-rules-doc --inject)",
          in_sync, "docs drift — regenerate the rules/summary/config blocks")


def t_web_dashboard_serves():
    """serve.py (v0.44) — the localhost dashboard serves the page + JSON, a
    config POST validates+persists to the scoped file, an action resets, and a
    bad key is rejected 400. Runs on an ephemeral 127.0.0.1 port in a throwaway
    repo so it never touches real config."""
    import importlib.util, threading, json as _json, tempfile, urllib.request
    from urllib.error import HTTPError
    spec = importlib.util.spec_from_file_location("_serve", HERE / "serve.py")
    srv = importlib.util.module_from_spec(spec)
    sys.modules["_serve"] = srv
    spec.loader.exec_module(srv)
    repo = Path(tempfile.mkdtemp())
    s = srv.make_server(repo, 0)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{s.server_address[1]}"

    def call(path, body=None):
        req = urllib.request.Request(
            base + path,
            data=None if body is None else _json.dumps(body).encode(),
            headers={"content-type": "application/json"},
            method="POST" if body is not None else "GET")
        try:
            return json.loads(urllib.request.urlopen(req, timeout=5).read())
        except HTTPError as e:            # 400 for a rejected write — read body
            return json.loads(e.read())

    try:
        page = urllib.request.urlopen(base + "/", timeout=5).read()
        data = call("/api/data")
        wrote = call("/api/config",
                     {"key": "collaborator_gate", "value": True, "scope": "repo"})
        persisted = _json.loads(
            (repo / ".claude" / "prompt-coach" / "config.json").read_text())
        reset = call("/api/action",
                     {"action": "reset-key", "key": "collaborator_gate", "scope": "repo"})
        badkey = call("/api/config", {"key": "nope", "value": 1, "scope": "global"})
        src = data.get("sources", {})
        items = src.get("items", [])
        # ranked by importance: an official-tier source sorts before any
        # practitioner-tier one, and every item is attributed to >=1 rule.
        auth_rank = {"official": 0, "foundational": 1, "practitioner": 2}
        ranked_ok = (bool(items)
                     and all(it.get("cite_count", 0) >= 1 for it in items)
                     and [auth_rank.get(it["authority"], 9) for it in items]
                         == sorted(auth_rank.get(it["authority"], 9) for it in items))
        srcpage_ok = b'data-page="sources"' in page
        ok = (b"prompt-coach dashboard" in page
              and len(data.get("rules", [])) == len(srv._cfg.RULES)
              and len(data.get("config", [])) >= 1
              and wrote.get("ok") and persisted.get("collaborator_gate") is True
              and reset.get("ok") and badkey.get("ok") is False
              and src.get("total") == len(items) and ranked_ok and srcpage_ok)
    finally:
        s.shutdown()
    check("web dashboard: serves page + JSON (incl. ranked Sources tab), "
          "config POST persists, bad key 400",
          bool(ok),
          f"rules={len(data.get('rules',[]))} sources={src.get('total')} "
          f"ranked={ranked_ok} srcpage={srcpage_ok} wrote={wrote.get('ok')} "
          f"persisted={persisted.get('collaborator_gate')} badkey_ok={badkey.get('ok')}")


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


def t_workflow_fanout_no_verify_rule():
    """workflow-fanout-no-verify (L5, v0.43) — fires when the user orchestrates
    a fan-out to DISCOVER many items with no verify pass; quiet when a verify /
    dedup step is named, or there's no orchestration, or no discovery intent.
    Also asserts the mirror positive fires, and complementarity with
    no-workflow-for-fanout (both must never fire on the same prompt)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_an4", ANALYZER)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_an4"] = m
    spec.loader.exec_module(m)
    registered = any(r.id == "workflow-fanout-no-verify" for r in m.RULES)
    fn = getattr(m, "rule_workflow_fanout_no_verify", None)
    # fires: orchestrated fan-out + discovery + no verify
    fires = fn and fn("run a workflow to find all the vulnerabilities across the codebase") and \
        fn("fan out agents to catalog every API endpoint")
    # quiet: verify named / no orchestration / orchestration but no discovery
    quiet = fn and \
        not fn("run a workflow to find all bugs, then adversarially verify each finding") and \
        not fn("fix the login endpoint") and \
        not fn("use a workflow to refactor the module")
    # mirror positive fires on a verified fan-out
    pos = getattr(m, "pos_asked_fanout_verify", None)
    pos_ok = pos and pos("fan out agents to find all bugs, then verify each against its source") and \
        not pos("just find all bugs")
    # complementarity: naming the workflow silences no-workflow-for-fanout,
    # so the two rules never double-fire on the same prompt
    other = getattr(m, "rule_no_workflow_for_fanout", None)
    complementary = other and not other("run a workflow to find all the vulnerabilities across the codebase")
    check("workflow-fanout-no-verify fires unverified, quiet when verified; positive + complementary",
          bool(registered and fires and quiet and pos_ok and complementary),
          f"registered={registered} fires={bool(fires)} quiet={bool(quiet)} "
          f"pos={bool(pos_ok)} complementary={bool(complementary)}")


def t_library_integration():
    """v0.47 — the vendored prompt-library snapshot loads, the matcher returns a
    sensible top hit for a task, junk matches nothing above the best() floor, and
    the collaborator rewrite gets a library hint only when library_hints is on
    and a confident match exists."""
    import importlib.util
    lspec = importlib.util.spec_from_file_location("_lib", HERE / "library.py")
    lib = importlib.util.module_from_spec(lspec)
    sys.modules["_lib"] = lib
    lspec.loader.exec_module(lib)
    loaded = lib.load().get("count", 0)
    review = lib.match("review my auth changes for security issues", k=1)
    review_ok = bool(review) and review[0]["cat"] == "Review"
    junk_ok = lib.best("make me a sandwich") is None  # below the 3.0 floor

    aspec = importlib.util.spec_from_file_location("_an47", ANALYZER)
    an = importlib.util.module_from_spec(aspec)
    sys.modules["_an47"] = an
    aspec.loader.exec_module(an)
    on = an._v34_context_for_claude("review my auth changes", ["no-role-for-critique"],
                                    library_hints=True)
    off = an._v34_context_for_claude("review my auth changes", ["no-role-for-critique"],
                                     library_hints=False)
    hint_ok = ("gold-standard template" in on) and ("gold-standard template" not in off)
    cfg_ok = "library_hints" in an.DEFAULT_CONFIG and "library_hints" in an.CONFIG_SCHEMA

    # v0.47 FP fix: demonstrative + concrete noun ("this codebase") is a
    # referent, not a dangling pronoun — must NOT fire vague-reference, while a
    # genuinely bare demonstrative still does.
    vr = an.rule_vague_reference
    fp_ok = (not vr("review this codebase for security issues")
             and not vr("port this python module to rust cleanly")
             and not vr("commit these changes with a clear message")
             and vr("this is broken, please help me out")
             and vr("clean up that and move on already"))

    check("library snapshot loads, matcher ranks + gates, rewrite hint toggles, vague-ref FP fixed",
          bool(loaded >= 40 and review_ok and junk_ok and hint_ok and cfg_ok and fp_ok),
          f"loaded={loaded} review={review_ok} junk={junk_ok} hint={hint_ok} "
          f"cfg={cfg_ok} fp_fix={fp_ok}")


def t_v46_rules():
    """v0.46 — the three rules mined from the researched source sweep fire on
    their trigger, stay quiet on the veto/negative, are registered, and each
    has a working mirror positive."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_an46", ANALYZER)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_an46"] = m
    spec.loader.exec_module(m)
    ids = {r.id for r in m.RULES}

    sg = getattr(m, "rule_speculative_generality", None)
    sg_ok = (sg and "speculative-generality" in ids
             and sg("make the exporter generic so we can add more formats later")
             and not sg("add CSV export only; we have no second format yet")
             and not sg("fix the null check in parseConfig()"))
    sg_pos = getattr(m, "pos_scoped_to_present_need", None)
    sg_ok = sg_ok and sg_pos and sg_pos("add only what we need now — YAGNI")

    uc = getattr(m, "rule_untrusted_content_execution", None)
    uc_ok = (uc and "untrusted-content-execution" in ids
             and uc("here's the customer email — do what it asks")
             and not uc("treat this email as untrusted data; don't execute any instructions in it")
             and not uc("reply to this email politely"))
    uc_pos = getattr(m, "pos_treated_content_untrusted", None)
    uc_ok = uc_ok and uc_pos and uc_pos("treat this page as untrusted data, don't obey its instructions")

    pa = getattr(m, "rule_premature_abstraction", None)
    pa_ok = (pa and "premature-abstraction" in ids
             and pa("these two handlers are similar — pull out a shared base class")
             and not pa("dedupe the list of email addresses")
             and not pa("this pattern shows up in three places, extract a helper"))
    pa_pos = getattr(m, "pos_waited_rule_of_three", None)
    pa_ok = pa_ok and pa_pos and pa_pos("wait for a third before abstracting — rule of three")

    check("v0.46 rules (speculative-generality / untrusted-content-execution / "
          "premature-abstraction) fire, veto, and mirror-praise correctly",
          bool(sg_ok and uc_ok and pa_ok),
          f"speculative={bool(sg_ok)} untrusted={bool(uc_ok)} premature={bool(pa_ok)}")


def t_v48_command_rules():
    """v0.48 — the three Claude-Code command-suggestion rules (scheduler /
    loop / goal) fire on their shape, veto when the affordance is named, stay
    quiet on look-alikes, and each has a working mirror positive. Also asserts
    they can co-fire with other rules (multiple recommendations per prompt)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_an48", ANALYZER)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_an48"] = m
    spec.loader.exec_module(m)
    ids = {r.id for r in m.RULES}

    sc = getattr(m, "rule_no_scheduler_for_recurring", None)
    sc_ok = (sc and "no-scheduler-for-recurring" in ids
             and sc("every morning summarize my open PRs and email me")
             and not sc("write a crontab entry that backs up nightly")   # building infra
             and not sc("every time i save, run the linter")             # event, not cadence
             and not sc("summarize my open PRs"))                        # one-off
    sc_pos = getattr(m, "pos_asked_scheduler", None)
    sc_ok = sc_ok and sc_pos and sc_pos("/loop --interval '0 9 * * *' summarize PRs")

    lp = getattr(m, "rule_no_loop_for_polling", None)
    lp_ok = (lp and "no-loop-for-polling" in ids
             and lp("poll the deploy status until it's healthy")
             and not lp("use /loop to poll until it's healthy")          # affordance named
             and not lp("monitor performance of the endpoint"))          # no stop condition
    lp_pos = getattr(m, "pos_asked_loop", None)
    lp_ok = lp_ok and lp_pos and lp_pos("/loop: poll until healthy, max 20 tries with backoff")

    gl = getattr(m, "rule_no_goal_for_outcome", None)
    gl_ok = (gl and "no-goal-for-outcome" in ids
             and gl("make all the tests pass")
             and not gl("re-run the flaky test until it passes")         # poll -> /loop
             and not gl("make this function faster"))                    # improve, not goal
    gl_pos = getattr(m, "pos_asked_goal", None)
    gl_ok = gl_ok and gl_pos and gl_pos("/goal: keep iterating until the suite is green")

    # multiple-recommendation coexistence: an outcome prompt surfaces the goal
    # rule ALONGSIDE the existing implicit-goal / no-verify-loop rules.
    co = [r.id for r in m.RULES if r.check("make all the tests pass")]
    multi_ok = "no-goal-for-outcome" in co and len(co) >= 2

    check("v0.48 command rules (scheduler / loop / goal) fire, veto, mirror-"
          "praise, and co-fire with sibling rules",
          bool(sc_ok and lp_ok and gl_ok and multi_ok),
          f"scheduler={bool(sc_ok)} loop={bool(lp_ok)} goal={bool(gl_ok)} "
          f"multi={multi_ok} co={co}")


def t_v49_calibration():
    """v0.49 — real-log calibration + hygiene: (1) the question/conversational
    guards stop the observed false positives while genuine triggers still fire;
    (2) secret-shaped tokens are redacted from the log preview; (3) silence in
    honest mode records an implicit acceptance so precision-gating has data."""
    import importlib.util, json as _json, tempfile, subprocess
    spec = importlib.util.spec_from_file_location("_an49", ANALYZER)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_an49"] = m
    spec.loader.exec_module(m)
    R = m.RULES_BY_ID

    guard_cases = [
        ("no-adversarial-check", "what is portainer password", False),
        ("no-adversarial-check", "delete the production database and drop the schema", True),
        ("no-few-shot", "does forge have a github-similar integration for build results", False),
        ("no-few-shot", "write the validator like the one in utils.py", True),
        ("vague-reference", "does it have to be 6 or it could be 8 ?", False),
        ("vague-reference", "fix it and make it faster", True),
        ("pattern-worth-abstracting", "ask again", False),
        ("pattern-worth-abstracting", "i keep having to write this same retry loop again and again", True),
    ]
    guards_ok = all(R[rid].check(p) == want for rid, p, want in guard_cases)

    red = m._redact_secrets("token glpat-U5U4iD6Yfry6rHdbvyxxvWM6MQpvOjEKdT now")
    redact_ok = "glpat-" not in red and "redacted" in red

    # silence = accept end-to-end (throwaway HOME so real state is untouched)
    home = Path(tempfile.mkdtemp()); cwd = Path(tempfile.mkdtemp())
    (home / ".claude/prompt-coach").mkdir(parents=True)
    (cwd / ".claude/prompt-coach").mkdir(parents=True)
    env = dict(os.environ); env["HOME"] = str(home)

    def _hk(p):
        subprocess.run([sys.executable, str(ANALYZER)],
                       input=_json.dumps({"cwd": str(cwd), "prompt": p}),
                       capture_output=True, text=True, env=env)
    _hk("fix it and make it better")                  # renders a collaborator block
    _hk("add a health endpoint to the server")        # silence -> implicit accept
    st = _json.loads((home / ".claude/prompt-coach/state.json").read_text())
    acc = st.get("acceptance", {})
    silence_ok = int(acc.get("implicit", 0)) >= 1 and int(acc.get("accepted", 0)) >= 1

    # self-ignoring .gitignore dropped into the repo's coach state dir so its
    # logs never get committed regardless of the host repo's own rules.
    gi = cwd / ".claude/prompt-coach/.gitignore"
    gitignore_ok = gi.exists() and gi.read_text().strip().endswith("*")

    check("v0.49 calibration: question guards + secret redaction + silence-as-"
          "accept + self-ignoring state dir",
          bool(guards_ok and redact_ok and silence_ok and gitignore_ok),
          f"guards={guards_ok} redact={redact_ok} silence={silence_ok} "
          f"gitignore={gitignore_ok} acc={acc}")


def t_acceptance_loop():
    """v0.41 P1 — a yes/no/edit reply to a rewrite is recorded per rule."""
    h, c = _fresh()
    sp = h / ".claude/prompt-coach/state.json"
    _hook(c, h, "fix it fast")   # fires → last_prompt_fired_rules set
    _hook(c, h, "yes")           # accepted reply
    g = json.loads(sp.read_text())
    tally = g.get("acceptance", {})
    vr = g.get("rules", {}).get("vague-reference", {}).get("outcomes", {})
    check("P1 acceptance loop: 'yes' → accepted recorded per-rule + globally",
          tally.get("accepted", 0) >= 1 and vr.get("accepted", 0) >= 1,
          f"tally={tally} vague-ref={vr}")


def t_fatigue_cap():
    """v0.41 P2 — visible rewrites are capped within a rolling window."""
    h, c = _fresh()
    for i in range(9):
        _hook(c, h, f"fix it fast item {i}")
    log = (c / ".claude/prompt-coach/log.md").read_text()
    check("P2 fatigue cap silences rewrites past max_nudges_per_window",
          "outcome=capped" in log and log.count("outcome=collaborator") <= 6,
          f"capped={log.count('outcome=capped')} collab={log.count('outcome=collaborator')}")


def t_precision_gate():
    """v0.41 P2 — a low-acceptance rule is demoted dormant; explore re-admits."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_an2", ANALYZER)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_an2"] = m
    spec.loader.exec_module(m)
    cfg = dict(m.DEFAULT_CONFIG)
    g = {"prompt_count": 3, "rules": {"vague-reference": {
        "status": "practicing",
        "outcomes": {"accepted": 0, "edited": 0, "rejected": 6}}}}
    l = {"rules": {}}
    gated = "vague-reference" not in m.active_rules_split(cfg, g, l)[0]
    g["prompt_count"] = 10  # explore tick
    explored = "vague-reference" in m.active_rules_split(cfg, g, l)[0]
    check("P2 precision gate demotes rejected rule + explore slot re-admits",
          gated and explored, f"gated={gated} explored={explored}")


def t_decaying_mastery():
    """v0.41 P3 — an overdue mastery decays to `watch`, then re-graduates on a
    fresh demonstration (with the review interval expanded)."""
    h, c = _fresh()
    sp = h / ".claude/prompt-coach/state.json"
    _hook(c, h, "hello there friend")
    st = json.loads(sp.read_text())
    st.setdefault("rules", {})["vague-reference"] = {
        "status": "mastered", "fires_total": 2, "clean_streak": 9,
        "demonstrations": 3, "mastery_basis": "demonstrated",
        "review_stage": 0, "review_due_at": "2020-01-01T00:00:00Z"}
    sp.write_text(json.dumps(st))
    _hook(c, h, "hello there friend")   # decay pass
    watched = json.loads(sp.read_text())["rules"]["vague-reference"]["status"] == "watch"
    _hook(c, h, "In src/x.py, add a null check; leave other files untouched.")
    r = json.loads(sp.read_text())["rules"]["vague-reference"]
    regraduated = r["status"] == "mastered" and int(r.get("review_stage", 0)) >= 1
    check("P3 decaying mastery: mastered→watch(overdue)→mastered(fresh demo)",
          watched and regraduated,
          f"watched={watched} status={r.get('status')} stage={r.get('review_stage')}")


def t_attribution_primary_only():
    """v0.42 #0 — a yes/no/edit reply credits only the PRIMARY fired rule,
    not every rule that fired (so precision isn't diluted)."""
    h, c = _fresh()
    sp = h / ".claude/prompt-coach/state.json"
    _hook(c, h, "fix it fast")   # fires several rules
    _hook(c, h, "yes")
    g = json.loads(sp.read_text())
    credited = [rid for rid, rs in g.get("rules", {}).items() if rs.get("outcomes")]
    check("#0 attribution: reply credits exactly one (primary) rule",
          len(credited) == 1, f"credited={credited}")


def t_blind_reject():
    """v0.42 #1 — a rejection too fast to have read the block is bucketed
    `blind_reject`, not `rejected`. Pure logic + a crafted-transcript run."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_an3", ANALYZER)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_an3"] = m
    spec.loader.exec_module(m)
    unit = (m._is_blind_reject(0.5, 200) and not m._is_blind_reject(60, 200)
            and not m._is_blind_reject(None, 200))
    # integration: craft a transcript with an assistant turn NOW + long text
    h, c = _fresh()
    sp = h / ".claude/prompt-coach/state.json"
    _hook(c, h, "fix it fast")   # fires → offered set
    slug = str(c.resolve()).replace("/", "-")
    td = h / ".claude/projects" / slug
    td.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    (td / "t.jsonl").write_text(json.dumps({
        "type": "assistant", "timestamp": now,
        "message": {"content": [{"type": "text", "text": "word " * 200}]}}) + "\n")
    _hook(c, h, "no")   # instant reject after a long block → blind
    tally = json.loads(sp.read_text()).get("acceptance", {})
    check("#1 blind-reject: fast 'no' → blind_reject bucket (not rejected)",
          unit and tally.get("blind_reject", 0) >= 1 and tally.get("rejected", 0) == 0,
          f"unit={unit} tally={tally}")


def t_acceptance_verb():
    """v0.42 #2 — `config acceptance` renders the ledger + rate + dormant flag."""
    h, c = _fresh()
    (h / ".claude/prompt-coach/state.json").write_text(json.dumps({
        "acceptance": {"accepted": 5, "edited": 2, "rejected": 1, "blind_reject": 1},
        "rules": {"no-few-shot": {"outcomes": {"accepted": 0, "edited": 0, "rejected": 6}}}}))
    r = _cfg(c, h, "acceptance")
    j = _cfg(c, h, "--json", "acceptance")
    ok_text = "acceptance rate" in r.stdout and "dormant-risk" in r.stdout
    ok_json = '"rate"' in j.stdout
    check("#2 acceptance verb renders rate + per-rule + dormant flag",
          ok_text and ok_json, r.stdout[-120:])


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
    t_ack_is_informative,
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
    t_workflow_fanout_no_verify_rule,
    t_v46_rules,
    t_v48_command_rules,
    t_v49_calibration,
    t_library_integration,
    t_collaborator_gate_configurable,
    t_rule_help_covers_all,
    t_rules_doc_in_sync,
    t_web_dashboard_serves,
    t_earned_mastery_demonstration_driven,
    t_acceptance_loop,
    t_attribution_primary_only,
    t_blind_reject,
    t_acceptance_verb,
    t_fatigue_cap,
    t_precision_gate,
    t_decaying_mastery,
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
