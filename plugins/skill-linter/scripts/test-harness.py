#!/usr/bin/env python3
"""skill-linter release gate — run with `make test-linter`.

A linter earns trust by not crying wolf, so roughly half of these checks assert
that something does NOT fire. The false-positive cases are the ones worth having:
they are what stop people from learning to ignore the output.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("_lint", HERE / "lint_skills.py")
lint = importlib.util.module_from_spec(_spec)
sys.modules["_lint"] = lint
_spec.loader.exec_module(lint)

_failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✓' if ok else '✗'} {name}")
    if not ok:
        _failures.append(name)
        if detail:
            print(f"      {detail}")


def skill(tmp: Path, name: str, front: str, body: str = "") -> Path:
    d = tmp / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\n{front}\n---\n\n{body}\n", encoding="utf-8")
    return d / "SKILL.md"


def rules_for(p: Path, learned=()) -> set[str]:
    sk = lint.load_skill(p)
    return {f.rule for f in lint.check(sk) + lint.apply_learned(sk, list(learned))}


GOOD = ('description: Use when the user says "lint my skills", "check SKILL.md", or asks '
        'whether a skill conforms. Audits skill files against published authoring guidance.')
BODY = "Read the target skill.\n\n" + "Explain the finding and the reasoning behind it. " * 12


# --------------------------------------------------------------------------

def t_frontmatter_shapes():
    """Real skills use plain, quoted, and folded scalars — all must parse."""
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        plain = skill(tmp, "a", f"name: a\n{GOOD}", BODY)
        folded = skill(tmp, "b", "name: b\ndescription: >\n  Use when the user says \"x\".\n"
                                 "  Second line folds into one.", BODY)
        quoted = skill(tmp, "c", 'name: c\ndescription: "Use when the user says \\"go\\"."', BODY)
        ok = (lint.load_skill(plain).name == "a"
              and "folds into one" in lint.load_skill(folded).description
              and lint.load_skill(folded).description.count("\n") == 0
              and lint.load_skill(quoted).description.startswith("Use when"))
        check("plain, folded (>) and quoted frontmatter all parse", ok,
              repr(lint.load_skill(folded).description))


def t_frontmatter_failures():
    """A malformed header is an error, and it stops the run — every later rule
    would just be noise derived from a file we could not read."""
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        (tmp / "none").mkdir()
        (tmp / "none" / "SKILL.md").write_text("# no frontmatter\n")
        (tmp / "open").mkdir()
        (tmp / "open" / "SKILL.md").write_text("---\nname: open\n\nbody\n")
        r1 = rules_for(tmp / "none" / "SKILL.md")
        r2 = rules_for(tmp / "open" / "SKILL.md")
        check("missing / unclosed frontmatter is a single error, not a cascade",
              r1 == {"frontmatter-invalid"} and r2 == {"frontmatter-invalid"},
              f"{r1} {r2}")


def t_colon_in_unquoted_value_is_an_error():
    """The miss that shipped. This linter's own description ended with
    "Learns: a defect it failed to catch becomes a new rule." — a bare `word: `
    inside an unquoted scalar, which real YAML rejects outright. The skill
    loaded with no metadata and could never have triggered, and the linter
    called it clean, because this parser is lenient where YAML is not."""
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        bad = skill(tmp, "leaky", 'name: leaky\n' + GOOD +
                    "\n  Learns: a defect it failed to catch becomes a new rule.", BODY)
        got = rules_for(bad)
        check("a bare `word: ` in an unquoted value is reported as invalid frontmatter",
              got == {"frontmatter-invalid"}, f"got {sorted(got)}")

    # ...but a colon that YAML tolerates must not be flagged, or every
    # description mentioning a URL or a ratio becomes a false positive.
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        ok = skill(tmp, "fine", 'name: fine\n' + GOOD +
                   "\n  See https://example.com/docs for the 3:1 ratio.", BODY)
        check("a tolerated colon (URL, ratio) is not flagged",
              "frontmatter-invalid" not in rules_for(ok), str(sorted(rules_for(ok))))


def t_matches_real_yaml():
    """The parser is hand-rolled so the linter runs without pyyaml. That is only
    safe if it agrees with real YAML on what is valid — otherwise it launders
    broken frontmatter as clean, which is worse than not checking."""
    try:
        import yaml
    except ImportError:
        check("hand-rolled parser agrees with real YAML", True, "pyyaml absent — skipped")
        return
    cases = [
        ('name: a\ndescription: Use when the user says "go".', True),
        ('name: a\ndescription: Use when asked.\n  Learns: a thing happens here.', False),
        ('name: a\ndescription: >\n  Use when asked. Folded body: still fine.', True),
    ]
    mism = []
    for block, want_ok in cases:
        _, _, _, err = lint.parse_frontmatter(f"---\n{block}\n---\n\nbody\n")
        try:
            yaml.safe_load(block); yaml_ok = True
        except Exception:
            yaml_ok = False
        if (not err) != yaml_ok or yaml_ok != want_ok:
            mism.append(f"{block[:40]!r} lint_ok={not err} yaml_ok={yaml_ok}")
    check("hand-rolled parser agrees with real YAML on valid/invalid", not mism,
          " | ".join(mism))


def t_name_must_match_directory():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        p = skill(tmp, "real-name", f"name: other-name\n{GOOD}", BODY)
        check("frontmatter name is checked against the directory",
              "name-mismatch" in rules_for(p))


def t_description_rules():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        cases = {
            "no-trigger": ("description: Scaffolds an application from scratch. Invoke explicitly.",
                           "description-no-trigger"),
            "first-person": ('description: Use when asked. I can help you write skills, '
                             'and we will iterate on "the draft" together.', "description-first-person"),
            "workflow": ('description: Use for TDD — first write the test, then watch it '
                         'fail, then write "the code".', "description-recites-workflow"),
        }
        for dirname, (front, want) in cases.items():
            p = skill(tmp, dirname, f"name: {dirname}\n{front}", BODY)
            got = rules_for(p)
            check(f"description rule fires: {want}", want in got, f"got {sorted(got)}")


def t_clean_skill_is_silent():
    """The most important assertion in the file. A linter that flags a good skill
    is worse than no linter, because people stop reading it."""
    with tempfile.TemporaryDirectory() as t:
        p = skill(Path(t), "tidy", f"name: tidy\n{GOOD}", BODY)
        got = rules_for(p)
        check("a well-formed skill produces no findings at all", got == set(), f"got {sorted(got)}")


def t_fenced_examples_are_not_findings():
    """Regression: the first run flagged screenshot-tour's Markdown template, whose
    `![hero](01-hero.gif)` is a file the skill tells you to CREATE. Skills also
    document bad patterns on purpose — flagging those punishes good writing."""
    body = BODY + """

```markdown
![hero](01-hero.gif)
![outcome](NN-outcome.png)
## When to use
See @skills/other/SKILL.md
ALWAYS NEVER MUST ALWAYS NEVER MUST ALWAYS NEVER MUST ALWAYS NEVER
```
"""
    with tempfile.TemporaryDirectory() as t:
        p = skill(Path(t), "fenced", f"name: fenced\n{GOOD}", body)
        got = rules_for(p)
        check("examples inside code fences never produce findings", got == set(),
              f"got {sorted(got)}")


def t_real_defects_outside_fences_still_fire():
    """The other half of the fence fix: stripping code must not blind the linter."""
    body = BODY + "\n\n## When to use\n\nSee @skills/other/SKILL.md and [gone](nope.md).\n"
    with tempfile.TemporaryDirectory() as t:
        p = skill(Path(t), "leaky", f"name: leaky\n{GOOD}", body)
        got = rules_for(p)
        check("the same defects in prose DO fire",
              {"trigger-info-in-body", "force-loading-link", "broken-reference"} <= got,
              f"got {sorted(got)}")


def t_existing_reference_is_not_flagged():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        p = skill(tmp, "refs", f"name: refs\n{GOOD}", BODY + "\n\nSee [notes](references/n.md).\n")
        (tmp / "refs" / "references").mkdir(parents=True)
        (tmp / "refs" / "references" / "n.md").write_text("# notes\n")
        check("a link to a file that exists is not reported",
              "broken-reference" not in rules_for(p))


def t_learned_rules_apply_and_survive_bad_input():
    """Learning is the point of the plugin, so the data path needs the same care
    as the code path — including a malformed rule not taking the run down."""
    with tempfile.TemporaryDirectory() as t:
        p = skill(Path(t), "learn", f"name: learn\n{GOOD}", BODY + "\n\nUse the frobnicator.\n")
        found = [{"id": "no-frobnicator", "scope": "body", "pattern": r"frobnicator",
                  "severity": "warn", "message": "frobnicator is deprecated"}]
        absent = [{"id": "needs-example", "scope": "body", "pattern": r"^## Example",
                   "absent": True, "severity": "info", "message": "no example section"}]
        broken = [{"id": "bad", "scope": "body", "pattern": "([unclosed"}]
        off = [dict(found[0], enabled=False)]
        check("a learned rule fires on a match", "no-frobnicator" in rules_for(p, found))
        check("a learned rule can fire on ABSENCE", "needs-example" in rules_for(p, absent))
        check("a broken learned pattern is reported, not raised",
              "learned-rule-broken" in rules_for(p, broken))
        check("a disabled learned rule stays quiet", "no-frobnicator" not in rules_for(p, off))


def t_learned_rules_file_is_optional_and_tolerant():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        missing = lint.load_learned(tmp / "nope.json")
        (tmp / "junk.json").write_text("{not json")
        junk = lint.load_learned(tmp / "junk.json")
        check("a missing or corrupt learned-rules file degrades to zero rules",
              missing == [] and junk == [])


def t_cli_exit_codes():
    """The gate contract: 0 clean, 1 on error, 1 on anything with --strict."""
    import contextlib, io

    def run(*extra):
        with contextlib.redirect_stdout(io.StringIO()):
            return lint.main([str(tmp), "--json", "--rules", str(tmp / "none.json"), *extra])

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        skill(tmp, "tidy", f"name: tidy\n{GOOD}", BODY)
        clean, strict_clean = run(), run("--strict")
        skill(tmp, "warny", "name: warny\ndescription: Scaffolds things. Invoke explicitly.", BODY)
        warn, strict_warn = run(), run("--strict")
        skill(tmp, "broken", "name: WRONG\ndescription: Use when testing exit codes please.", BODY)
        err = run()
        check("exit codes: clean=0, warn=0, warn+strict=1, error=1",
              (clean, strict_clean, warn, strict_warn, err) == (0, 0, 0, 1, 1),
              f"got {(clean, strict_clean, warn, strict_warn, err)}")


def t_agent_checks():
    """0.2.0 — agents/*.md are linted too. The rule that pays for it:
    `allowed-tools:` is the slash-command field; in an agent it is silently
    ignored and the agent runs with EVERY tool. Three shipped "read-only"
    agents could write, edit, and push, and the linter had no opinion."""
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); ad = tmp / "agents"; ad.mkdir()
        (ad / "auditor.md").write_text(
            "---\nname: auditor\ndescription: Audit things. Use this agent when auditing.\n"
            "allowed-tools: Read, Grep\n---\n\nbody\n")
        (ad / "runner.md").write_text(
            "---\nname: runner\ndescription: Use this agent when tests need running.\n"
            "tools: Read, Grep, Glob, Bash\n---\n\nbody\n")
        (ad / "typo.md").write_text(
            "---\nname: typo\ndescription: Use this agent when typos strike.\n"
            "tools: Read, Grpe\n---\n\nbody\n")
        (ad / "misnamed.md").write_text(
            "---\nname: other\ndescription: Use this agent when misnamed.\n---\n\nbody\n")

        sk, ag = lint.discover([str(tmp)])
        check("discover finds agents/*.md and no phantom skills",
              len(ag) == 4 and sk == [], f"skills={sk} agents={len(ag)}")

        def rules(name):
            return {f.rule for f in lint.check_agent(lint.load_skill(ad / name))}
        check("allowed-tools in an agent is an ERROR, not a style note",
              "agent-wrong-tools-field" in rules("auditor.md"))
        check("a correct agent (tools:, trigger, matching name) is clean",
              rules("runner.md") == set(), str(rules("runner.md")))
        check("a misspelled tool name is flagged",
              "agent-unknown-tool" in rules("typo.md"))
        check("agent name must match its filename",
              "name-mismatch" in rules("misnamed.md"))

    # role.md files must never be swept in as agents
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); rd = tmp / "skills" / "skeptic"; rd.mkdir(parents=True)
        (rd / "role.md").write_text("# skeptic\ncharter prose, no frontmatter\n")
        sk, ag = lint.discover([str(tmp)])
        check("role.md files are not treated as agents", ag == [], str(ag))


def t_dogfoods_this_repo():
    """The linter's own skill has to pass the linter. If the author cannot meet the
    bar, the bar is wrong — this is the check that keeps it honest."""
    own = HERE.parent / "skills" / "skill-linter" / "SKILL.md"
    if not own.exists():
        check("skill-linter's own SKILL.md passes clean", False, "SKILL.md not found")
        return
    got = rules_for(own)
    check("skill-linter's own SKILL.md passes clean", got == set(), f"got {sorted(got)}")


CHECKS = [
    t_frontmatter_shapes,
    t_frontmatter_failures,
    t_colon_in_unquoted_value_is_an_error,
    t_matches_real_yaml,
    t_name_must_match_directory,
    t_description_rules,
    t_clean_skill_is_silent,
    t_fenced_examples_are_not_findings,
    t_real_defects_outside_fences_still_fire,
    t_existing_reference_is_not_flagged,
    t_learned_rules_apply_and_survive_bad_input,
    t_learned_rules_file_is_optional_and_tolerant,
    t_cli_exit_codes,
    t_agent_checks,
    t_dogfoods_this_repo,
]


def main() -> int:
    print("\n  skill-linter harness\n")
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
