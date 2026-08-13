#!/usr/bin/env python3
"""skill-linter — check SKILL.md files against the published skill-authoring guidance.

Every rule here traces to a source: Anthropic's `skill-creator`, `skill-development`,
or `writing-skills`. See references/rule-sources.md for the citation behind each id,
including the two places where the sources contradict each other and how that is
resolved.

What this does NOT do: tell you whether a skill actually works. Form is cheap to
check and behaviour is not — the linter catches the mechanical defects so the
expensive eval loop (skill-creator's real contribution) is spent on judgment.

    lint_skills.py [PATH ...] [--json] [--strict] [--rules FILE] [--only ID,...]

With no PATH, walks the current directory for */SKILL.md. Exit 1 on any error
(or on any finding at all with --strict), so it works as a gate.

Learned rules live OUTSIDE this directory — in the consuming repo's
`.claude/skill-linter/learned-rules.json` — because an installed plugin sits in a
read-only cache. That file is how the linter grows: see the skill's Learning loop.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ERROR, WARN, INFO = "error", "warn", "info"
LEVELS = (ERROR, WARN, INFO)

# skill-creator: "Keep SKILL.md under 500 lines".
MAX_BODY_LINES = 500
# skill-creator: "For large reference files (>300 lines), include a table of contents".
REF_TOC_LINES = 300
# skill-development: "Body is focused and lean (1,500-2,000 words ideal, <5k max)".
MAX_BODY_WORDS = 5000


@dataclass
class Finding:
    skill: str
    rule: str
    level: str
    message: str
    hint: str = ""
    line: int = 0


@dataclass
class Skill:
    path: Path                       # the SKILL.md itself
    dir: Path
    name: str = ""
    description: str = ""
    frontmatter: dict = field(default_factory=dict)
    fm_error: str = ""
    body: str = ""
    body_line0: int = 0              # 1-indexed line where the body starts
    text: str = ""

    @property
    def label(self) -> str:
        return f"{self.dir.parent.parent.name}/{self.dir.name}" \
            if self.dir.parent.name == "skills" else self.dir.name


# --------------------------------------------------------------- frontmatter

def _scalar(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    return raw


def parse_frontmatter(text: str) -> tuple[dict, str, int, str]:
    """Minimal YAML-subset parser: `key: value`, plus `>` and `|` block scalars.

    Hand-rolled rather than pyyaml so the linter runs anywhere with bare Python —
    a gate that only works when a dependency happens to be installed is not a gate.
    Anything it cannot parse is reported rather than guessed at.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text, 1, "no YAML frontmatter (a SKILL.md must open with ---)"
    end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "---"), None)
    if end is None:
        return {}, text, 1, "frontmatter is never closed (missing the second ---)"

    # A description routinely wraps over several lines, so all three scalar
    # shapes have to work: plain (`key: text` continued by indented lines),
    # folded (`>`), and literal (`|`). PLAIN is where the danger is — see below.
    PLAIN, FOLDED, LITERAL = "plain", "folded", "literal"
    # Real YAML rejects a bare `word: ` inside a plain scalar with "mapping
    # values are not allowed here", and Claude Code then loads the skill with
    # EMPTY metadata — it silently never triggers. This linter's own description
    # shipped with "Learns: a defect it failed to catch becomes a new rule." and
    # was called clean, because a lenient parser launders broken frontmatter.
    NESTED_MAP = re.compile(r"^\s*([A-Za-z][\w -]{0,40}):(\s|$)")

    fm: dict[str, str] = {}
    key, buf, mode = None, [], PLAIN

    def flush() -> None:
        if key is None:
            return
        joined = "\n".join(buf) if mode is LITERAL else " ".join(b for b in buf if b)
        fm[key] = _scalar(joined.strip()) if mode is PLAIN else joined.strip()

    for raw in lines[1:end]:
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", raw)
        if m and not raw.startswith((" ", "\t")):
            flush()
            key, rest = m.group(1), m.group(2).strip()
            if rest in (">", "|", ">-", "|-", ">+", "|+"):
                buf, mode = [], (FOLDED if rest[0] == ">" else LITERAL)
            else:
                buf, mode = [rest], PLAIN
        elif key is not None:
            if mode is PLAIN and (hit := NESTED_MAP.match(raw)):
                return {}, "\n".join(lines[end + 1:]), end + 2, (
                    f"`{hit.group(1)}:` on a continuation line of `{key}` — YAML reads "
                    f"that as a nested mapping and rejects the whole block, so the "
                    f"skill loads with no name or description at all and can never "
                    f"trigger. Quote the value, use a `>` block, or reword it")
            buf.append(raw.strip())
        elif raw.strip():
            return {}, "\n".join(lines[end + 1:]), end + 2, \
                f"cannot parse frontmatter line: {raw.strip()[:60]!r}"
    flush()
    return fm, "\n".join(lines[end + 1:]), end + 2, ""


# --------------------------------------------------------------- rule helpers

TRIGGER = re.compile(
    r"\b(use (this |it |the )?(skill )?(when|whenever|before|after|for)"
    r"|invoke (this |it |automatically |explicitly |proactively )*(when|whenever)"
    r"|should be used when|trigger(s|ed)? (on|when|even)"
    r"|when the user (says|asks|mentions|wants|requests)"
    r"|use proactively)", re.I)

QUOTED = re.compile(r'"[^"\n]{3,}"|“[^”\n]{3,}”|`[^`\n]{3,}`')
FIRST_PERSON = re.compile(r"(?<![\w'])(I|I'll|I'm|my|me|we|we'll|our)(?![\w'])", re.I)
SECOND_PERSON = re.compile(r"(?<![\w'])(you|your|yours|you'll|you're)(?![\w'])", re.I)
# writing-skills' central finding: a description that recites the steps becomes a
# shortcut agents take instead of reading the skill.
WORKFLOW = re.compile(
    r"(\bfirst\b[^.]{0,60}\bthen\b|\bthen\b[^.]{0,40}\bthen\b|→[^.]*→"
    r"|\bstep 1\b|\b1\.\s.+\b2\.\s)", re.I)
SHOUTY = re.compile(r"(?<![\w-])(ALWAYS|NEVER|MUST NOT|MUST|DO NOT|REQUIRED)(?![\w-])")
FORCE_LOAD = re.compile(r"(?<![\w`/])@[\w./-]*(skills?|SKILL\.md)[\w./-]*", re.I)
BODY_TRIGGER_HEADING = re.compile(
    r"^#{2,4}\s*(when to (use|invoke|trigger)|use (this|it) when|triggers?)\b", re.I | re.M)
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)#][^)]*)\)")
SEEN_TOC = re.compile(r"^#{1,3}\s*(table of contents|contents|toc)\b", re.I | re.M)


def strip_quoted(d: str) -> str:
    """Drop quoted user phrases before checking grammatical person.

    A description is *supposed* to quote what the user types, and real users say
    "lint my skills" or "does this look right to you". Those pronouns belong to
    the user's voice, not the author's — flagging them punishes exactly the
    phrase-listing the linter asks for two rules earlier.
    """
    return QUOTED.sub(" ", d)


def _kebab(s: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", s))


FENCE = re.compile(r"^([ \t]*)(`{3,}|~{3,})[^\n]*\n.*?^\1?\2[ \t]*$", re.S | re.M)


def strip_fences(body: str) -> str:
    """Blank out fenced blocks, preserving line numbers.

    Prose rules must not fire on code. A skill that documents a bad pattern shows
    it in a fence — `writing-skills` is full of ❌ examples, and `screenshot-tour`
    embeds a Markdown template whose `![hero](01-hero.gif)` is a file the skill
    tells you to *create*, not one it expects to find. Flagging either is noise
    that trains people to ignore the linter.
    """
    return FENCE.sub(lambda m: "\n" * m.group(0).count("\n"), body)


# --------------------------------------------------------------- shipped rules

def check(sk: Skill) -> list[Finding]:
    """Rules ship as code, not data, so they are reviewable in a diff and testable.

    Learned rules are data (see apply_learned) — that split keeps the graduation
    path honest: a learned rule earns its way into this function.
    """
    out: list[Finding] = []
    add = lambda r, lv, m, h="", ln=0: out.append(Finding(sk.label, r, lv, m, h, ln))
    d, body = sk.description, sk.body
    prose = strip_fences(body)     # every content rule below reads prose, not code

    # --- structure ---------------------------------------------------------
    if sk.fm_error:
        add("frontmatter-invalid", ERROR, sk.fm_error,
            "name and description are the only always-loaded part of a skill; if they "
            "do not parse, the skill cannot be selected at all", 1)
        return out                     # nothing else is meaningful without it

    if not sk.name:
        add("name-missing", ERROR, "frontmatter has no `name`", line=1)
    elif sk.name != sk.dir.name:
        add("name-mismatch", ERROR,
            f"frontmatter name `{sk.name}` does not match directory `{sk.dir.name}`",
            "the loader keys off the directory; a mismatch makes the skill unaddressable", 1)
    elif not _kebab(sk.name):
        add("name-format", WARN, f"`{sk.name}` is not kebab-case",
            "lowercase-with-hyphens is what every other skill uses, and the name is "
            "typed by users in slash commands", 1)

    if not d:
        add("description-missing", ERROR, "frontmatter has no `description`",
            "the description is the ONLY thing Claude sees when deciding to load the "
            "skill — without it the skill never triggers", 1)
        return out

    if len(body.split()) < 50:
        add("body-thin", WARN, f"body is only {len(body.split())} words",
            "if everything fits in the description, the skill may not be earning its slot")

    # --- description quality ----------------------------------------------
    words = len(d.split())
    if words < 10:
        add("description-vague", WARN, f"description is only {words} words",
            "too short to carry both what it does and when it applies")
    if not TRIGGER.search(d):
        add("description-no-trigger", WARN, "description never says WHEN to use the skill",
            'add explicit triggering conditions — "Use when …", "…should be used when …". '
            "Claude undertriggers skills, so this is the single highest-value fix")
    if not QUOTED.search(d):
        add("description-no-phrases", INFO, "description quotes no user phrases",
            'list what a user would actually type — "map this out", "add a hook" — so '
            "the description matches real prompts rather than a topic label")
    voice = strip_quoted(d)      # the author's words only, not the user's
    if FIRST_PERSON.search(voice):
        add("description-first-person", WARN,
            f"description uses first person ({FIRST_PERSON.search(voice).group(0)!r})",
            "the description is injected into a system prompt; write it in third person")
    if SECOND_PERSON.search(voice):
        add("description-second-person", INFO,
            f"description uses second person ({SECOND_PERSON.search(voice).group(0)!r})",
            'prefer "Use when the user asks…" over "Use this when you want…" — third '
            "person reads correctly wherever the description is injected")
    if WORKFLOW.search(voice):
        add("description-recites-workflow", WARN,
            "description summarises the skill's steps",
            "an agent that can read the workflow in the description may act on it and "
            "never open the skill. State the purpose and the triggers; leave the steps "
            "to the body")

    # --- body -------------------------------------------------------------
    nlines = body.count("\n") + 1
    if nlines > MAX_BODY_LINES:
        add("body-too-long", WARN, f"body is {nlines} lines (guideline: {MAX_BODY_LINES})",
            "move detail into references/ and point at it, so the whole file is not "
            "loaded every time the skill fires")
    nwords = len(body.split())
    if nwords > MAX_BODY_WORDS:
        add("body-too-many-words", WARN, f"body is {nwords} words (max {MAX_BODY_WORDS})")

    m = BODY_TRIGGER_HEADING.search(prose)
    if m:
        add("trigger-info-in-body", WARN,
            f"body has a {m.group(0).strip()!r} section",
            "the body is only read AFTER the skill is chosen, so triggering conditions "
            "kept here can never influence the decision — move them to the description",
            sk.body_line0 + prose[:m.start()].count("\n"))

    shouty = SHOUTY.findall(prose)
    if len(shouty) > 8:
        add("shouty-directives", INFO, f"{len(shouty)} all-caps directives in the body",
            "capitalised MUST/ALWAYS reads as distrust and tends to be skimmed; "
            "explaining why a constraint matters holds better")

    for fm in FORCE_LOAD.finditer(prose):
        add("force-loading-link", WARN, f"`{fm.group(0)}` force-loads another file",
            "@-links pull the target into context immediately, spending tokens before "
            "the skill knows it needs them — name the skill instead",
            sk.body_line0 + prose[:fm.start()].count("\n"))

    # --- bundled resources -------------------------------------------------
    for lm in MD_LINK.finditer(prose):
        target = lm.group(1).split("#")[0].strip()
        if not target or "://" in target or target.startswith(("mailto:", "<")):
            continue
        if any(ch in target for ch in "*{}$") or target.startswith("~"):
            continue                                   # a glob or a placeholder
        if not (sk.dir / target).exists() and not (sk.dir.parent / target).exists():
            add("broken-reference", WARN, f"links to `{target}`, which does not exist",
                "a reference the model cannot open is worse than no reference",
                sk.body_line0 + prose[:lm.start()].count("\n"))

    for ref in sorted(sk.dir.glob("references/*.md")):
        rl = len(ref.read_text(encoding="utf-8", errors="replace").splitlines())
        if rl > REF_TOC_LINES and not SEEN_TOC.search(ref.read_text(encoding="utf-8", errors="replace")):
            add("reference-no-toc", INFO,
                f"references/{ref.name} is {rl} lines with no table of contents",
                "a long reference without a map forces a full read to find one section")
    return out


# --------------------------------------------------------------- learned rules

def load_learned(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  ! ignoring {path}: {exc}", file=sys.stderr)
        return []
    return [r for r in data.get("rules", []) if r.get("enabled", True)]


def apply_learned(sk: Skill, rules: list[dict]) -> list[Finding]:
    """Rules the linter was taught after it missed something.

    Kept as data so a lesson can be recorded the moment it is learned, without
    editing this file. A rule that proves itself gets promoted into check().
    """
    out = []
    for r in rules:
        if not r.get("enabled", True):
            continue
        scope = r.get("scope", "body")
        hay = {"description": sk.description, "body": sk.body,
               "name": sk.name, "all": sk.text}.get(scope, sk.body)
        try:
            hit = re.search(r["pattern"], hay, re.I | re.M) is not None
        except re.error as exc:
            out.append(Finding(sk.label, "learned-rule-broken", INFO,
                               f"learned rule {r.get('id')!r} has a bad pattern: {exc}"))
            continue
        if hit is not bool(r.get("absent", False)):
            out.append(Finding(sk.label, r.get("id", "learned"),
                               r.get("severity", WARN) if r.get("severity") in LEVELS else WARN,
                               r.get("message", "learned rule matched"),
                               r.get("why", "")))
    return out


# --------------------------------------------------------------- driver

def load_skill(p: Path) -> Skill:
    text = p.read_text(encoding="utf-8", errors="replace")
    fm, body, line0, err = parse_frontmatter(text)
    return Skill(path=p, dir=p.parent, name=str(fm.get("name", "")),
                 description=" ".join(str(fm.get("description", "")).split()),
                 frontmatter=fm, fm_error=err, body=body, body_line0=line0, text=text)


def discover(paths: list[str]) -> list[Path]:
    found: list[Path] = []
    for raw in paths or ["."]:
        p = Path(raw)
        if p.is_file() and p.name == "SKILL.md":
            found.append(p)
        elif (p / "SKILL.md").is_file():
            found.append(p / "SKILL.md")
        elif p.is_dir():
            found += [q for q in p.rglob("SKILL.md")
                      if not any(part in {"node_modules", ".git"} for part in q.parts)]
    return sorted(set(found))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="*", help="SKILL.md files, skill dirs, or a tree to walk")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    ap.add_argument("--rules", default=".claude/skill-linter/learned-rules.json",
                    help="learned-rule file (default: %(default)s)")
    ap.add_argument("--only", help="comma-separated rule ids to report")
    args = ap.parse_args(argv)

    files = discover(args.paths)
    if not files:
        print("no SKILL.md found", file=sys.stderr)
        return 2

    learned = load_learned(Path(args.rules))
    findings: list[Finding] = []
    for f in files:
        sk = load_skill(f)
        findings += check(sk) + apply_learned(sk, learned)

    if args.only:
        keep = {s.strip() for s in args.only.split(",")}
        findings = [f for f in findings if f.rule in keep]

    counts = {lv: sum(1 for f in findings if f.level == lv) for lv in LEVELS}

    if args.json:
        print(json.dumps({
            "skills": len(files), "counts": counts, "learned_rules": len(learned),
            "findings": [vars(f) for f in findings],
        }, indent=2))
    else:
        by_skill: dict[str, list[Finding]] = {}
        for f in findings:
            by_skill.setdefault(f.skill, []).append(f)
        mark = {ERROR: "✗", WARN: "!", INFO: "·"}
        for skill in sorted(by_skill):
            print(f"\n  {skill}")
            for f in sorted(by_skill[skill], key=lambda x: LEVELS.index(x.level)):
                loc = f":{f.line}" if f.line else ""
                print(f"    {mark[f.level]} {f.rule}{loc} — {f.message}")
                if f.hint:
                    for i, ln in enumerate(_wrap(f.hint, 84)):
                        print(f"        {'→ ' if i == 0 else '  '}{ln}")
        clean = len(files) - len(by_skill)
        print(f"\n  {len(files)} skills · {clean} clean · "
              f"{counts[ERROR]} errors · {counts[WARN]} warnings · {counts[INFO]} info"
              + (f" · {len(learned)} learned rules" if learned else ""))

    if counts[ERROR]:
        return 1
    return 1 if args.strict and (counts[WARN] or counts[INFO]) else 0


def _wrap(s: str, w: int) -> list[str]:
    out, line = [], ""
    for word in s.split():
        if len(line) + len(word) + 1 > w:
            out.append(line); line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out


if __name__ == "__main__":
    raise SystemExit(main())
