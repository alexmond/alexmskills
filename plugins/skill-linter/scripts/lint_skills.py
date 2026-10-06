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
    # What a strict YAML reader sees that the string-only dict above hides:
    # {"quoted": keys whose value is always a string, "nested": {key: {sub: val}},
    #  "comment": {key: text a ` #` cut off}}.
    fm_extra: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        if self.dir.name == "agents":                      # plugins/X/agents/foo.md
            return f"{self.dir.parent.name}/agents/{self.path.stem}"
        return f"{self.dir.parent.parent.name}/{self.dir.name}" \
            if self.dir.parent.name == "skills" else self.dir.name


# --------------------------------------------------------------- frontmatter

def _scalar(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    return raw


# What YAML 1.2's core schema resolves an unquoted scalar to something OTHER
# than a string: null, booleans, ints, floats. `name: 2048` is the number 2048.
YAML_NONSTR = re.compile(
    r"^(?:~|null|Null|NULL|true|True|TRUE|false|False|FALSE"
    r"|[-+]?\d+|0o[0-7]+|0x[0-9a-fA-F]+"
    r"|[-+]?(?:\.\d+|\d+(?:\.\d*)?)(?:[eE][-+]?\d+)?"
    r"|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$")
# Inside an unquoted scalar, `: ` (or a trailing `:`) is the mapping indicator
# and ` #` opens a comment. Neither is text.
PLAIN_COLON = re.compile(r"(\S*):(?:\s|$)")
PLAIN_COMMENT = re.compile(r"(?:^|\s)#")
NESTED_CHILD = re.compile(r"^\s+([A-Za-z_][\w-]*):\s*(.*)$")


def parse_frontmatter(text: str, extra: dict | None = None) -> tuple[dict, str, int, str]:
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
    #
    # The first guard only looked at the START of a CONTINUATION line. A colon
    # on the key's own line, or mid-line, is the same error: a description
    # ending "…the built-in `init` skill: `init` bootstraps…" sat on one line,
    # passed, and was the one skill of 33 the skills CLI refused to list.
    QUOTED, FLOW = "quoted", "flow"   # "…" / '…' and [..] / {..}: a colon is text or syntax
    NESTED = "nested"          # `metadata:` with no value + indented children — valid YAML

    fm: dict[str, str] = {}
    info = extra if extra is not None else {}
    info.setdefault("quoted", set())
    info.setdefault("nested", {})
    info.setdefault("comment", {})
    info.setdefault("collection", set())
    key, buf, mode = None, [], PLAIN
    cut = False                # a ` #` comment already ended this plain scalar
    body, body_line = "\n".join(lines[end + 1:]), end + 2

    def plain(chunk: str, first: bool) -> tuple[str, str]:
        """One line of an unquoted scalar → (text YAML keeps, error)."""
        nonlocal cut
        if chunk.lstrip().startswith("#"):
            cut = True                 # a comment line ends the scalar, cutting nothing
            return "", ""
        if cut:
            return "", (
                f"text continues after a `#` comment inside the unquoted value of "
                f"`{key}` — a comment ends a plain scalar, so YAML rejects the lines "
                f"after it and the whole block with them. Quote the value or use a "
                f"`>` block")
        if not chunk.strip():
            return "", ""
        if c := PLAIN_COMMENT.search(chunk):
            info["comment"].setdefault(key, chunk[c.start():].strip())
            chunk, cut = chunk[:c.start()], True
        if hit := PLAIN_COLON.search(chunk):
            word = hit.group(1)[-40:]
            return "", (
                f"`{word}:` inside the unquoted value of `{key}` — YAML reads "
                f"that as a nested mapping and rejects the whole block. Every "
                f"strict reader (the `skills` CLI, anything on a real YAML "
                f"parser) then skips the skill outright; a lenient loader may "
                f"still take it, which is how this ships unnoticed. Quote the "
                f"value, use a `>` block, or reword it")
        return chunk.strip(), ""

    def flush() -> None:
        if key is None:
            return
        if mode is NESTED:
            rows = [b for b in buf if b.strip() and not b.lstrip().startswith("#")]
            if not rows:
                return
            if any(PLAIN_COLON.search(b) or b.lstrip().startswith("- ") for b in rows):
                # A sub-mapping or a list. Only its top level is ours to read.
                dent = min(len(b) - len(b.lstrip()) for b in rows)
                sub: dict[str, str] = {}
                for b in rows:
                    k = NESTED_CHILD.match(b)
                    if k and len(b) - len(b.lstrip()) == dent:
                        sub.setdefault(k.group(1), _scalar(k.group(2)))
                info["nested"][key] = sub
                info["collection"].add(key)
            else:
                # `description:` then the text on indented lines below — a plain
                # scalar that merely starts on the next line. Skipping it as a
                # "nested map" reported a present description as missing.
                fm[key] = " ".join(b.strip() for b in rows)
            return
        joined = "\n".join(buf) if mode is LITERAL else " ".join(b for b in buf if b)
        fm[key] = _scalar(joined.strip()) if mode in (PLAIN, QUOTED) else joined.strip()
        if mode in (QUOTED, FOLDED, LITERAL):
            info["quoted"].add(key)

    for raw in lines[1:end]:
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", raw)
        if m and not raw.startswith((" ", "\t")):
            flush()
            key, rest = m.group(1), m.group(2).strip()
            cut = False
            if re.fullmatch(r"[>|][-+]?\d?[-+]?", rest):
                buf, mode = [], (FOLDED if rest[0] == ">" else LITERAL)
            elif rest == "" or rest.startswith("#"):
                # An empty value followed by indented `sub: val` lines is a real
                # nested mapping (antfu's skills: `metadata:` / `  author: …`).
                # The guard below is only for text scalars that grow a colon —
                # firing here called three perfectly valid skills broken.
                buf, mode = [], NESTED
            elif rest[0] in "\"'":
                buf, mode = [rest], QUOTED
            elif rest[0] in "[{":
                buf, mode = [rest], FLOW
                info["collection"].add(key)
                if key == "metadata":
                    info["nested"][key] = dict(
                        (k, _scalar(v.strip())) for k, v in
                        re.findall(r"([A-Za-z_][\w-]*):\s*([^,}]*)", rest))
            else:
                kept, err = plain(rest, first=True)
                if err:
                    return {}, body, body_line, err
                buf, mode = [kept], PLAIN
        elif key is not None:
            if mode is NESTED:
                buf.append(raw)        # sorted out in flush(): a sub-mapping or a late-starting scalar
                continue
            if mode is PLAIN:
                kept, err = plain(raw, first=False)
                if err:
                    return {}, body, body_line, err
                buf.append(kept)
                continue
            buf.append(raw.strip())
        elif raw.strip() and not raw.lstrip().startswith("#"):
            return {}, body, body_line, \
                f"cannot parse frontmatter line: {raw.strip()[:60]!r}"
    flush()
    return fm, body, body_line, ""


# --------------------------------------------------------------- rule helpers

TRIGGER = re.compile(
    r"\b(use (this |it |the )?(skill |agent )?(when|whenever|before|after|for)"
    r"|invoke (this |it |automatically |explicitly |proactively )*(when|whenever)"
    r"|should be used when|trigger(s|ed)? (on|when|even)"
    r"|when the user (says|asks|mentions|wants|requests)"
    r"|load (this )?(skill )?when|use (this|it) to\b|use for\b"
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
# agentskills.io spec: 1-64 chars, no leading/trailing/consecutive hyphens.
NAME_SPEC = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# platform best-practices "Avoid" list, verbatim: helper/utils/tools/documents/data/files
GENERIC_NAMES = {"helper", "utils", "tools", "documents", "data", "files"}
# Real markup only: a closing tag, a self-closing tag, or a tag with attributes.
# Bare `<role>` / `<app>` placeholders are CLI-doc idiom, not XML — the first cut
# flagged five descriptions for writing "/roles:as <role>".
XML_TAG = re.compile(r"</[A-Za-z][\w-]*>|<[A-Za-z][\w-]*\s+[\w-]+=|<[A-Za-z][\w-]*\s*/>")
DRIVE_PATH = re.compile(r"\b[A-Za-z]:\\\w")
# Agent Skills spec's six portable frontmatter fields; anything else hard-fails
# claude.ai upload (code.claude.com). Claude Code itself accepts extras.
PORTABLE_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
# Fields Claude Code documents beyond the portable spec. A key in neither set is
# almost always a typo — and a typo'd `description` means the skill never fires.
CODE_KEYS = PORTABLE_KEYS | {
    # the full documented frontmatter table, code.claude.com/docs/en/skills
    "argument-hint", "arguments", "disable-model-invocation", "user-invocable",
    "disallowed-tools", "model", "effort", "context", "agent", "background",
    "hooks", "paths", "shell", "when_to_use",
}
# GitHub Copilot's "vague quality improvements" list — noise, not instruction.
VAGUE_EXHORT = re.compile(
    r"\b(be (more )?(accurate|careful|thorough)|don'?t (miss|make) any|do your best)\b", re.I)
DESC_MAX = 1024          # Agent Skills spec + platform best-practices hard cap
LISTING_MAX = 1536       # Claude Code truncates description+when_to_use here
BODY_HARD_LINES = 1000   # Copilot's documented ceiling; corroborates the 500 guideline
BODY_TOKEN_BUDGET = 5000 # progressive-disclosure Level-2 budget (both official sources)
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


INLINE_CODE = re.compile(r"`[^`\n]+`")


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

    # --- what a strict reader sees (source: vercel-labs/skills, skills.ts) ---
    ex = sk.fm_extra
    for k in ("name", "description"):
        raw = sk.frontmatter.get(k, "")
        if k in ex.get("collection", ()) or (
                raw and k not in ex.get("quoted", ()) and YAML_NONSTR.match(raw)):
            add("frontmatter-not-string", WARN,
                f"YAML reads `{k}` as a "
                f"{'list or mapping' if k in ex.get('collection', ()) else 'number, boolean or null'}"
                f", not text",
                "the skills CLI requires both fields to be strings and skips the skill "
                "otherwise — quote the value", 1)
        if k in ex.get("comment", {}):
            add("frontmatter-comment-cut", WARN,
                f"` #` starts a YAML comment, so `{k}` ends before "
                f"`{ex['comment'][k][:40]}`",
                "everything from the ` #` on is dropped without an error — quote the "
                "value or use a `>` block", 1)
    if ex.get("nested", {}).get("metadata", {}).get("internal", "").lower() == "true":
        add("metadata-internal", INFO,
            "`metadata.internal: true` hides this skill from `npx skills add`",
            "deliberate for work-in-progress skills; it is listed only with "
            "INSTALL_INTERNAL_SKILLS=1 or when asked for by name", 1)

    if not sk.name:
        add("name-missing", ERROR, "frontmatter has no `name`", ln=1)
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

    # --- spec limits (platform best-practices + agentskills.io) ------------
    if sk.name and (len(sk.name) > 64 or not NAME_SPEC.match(sk.name)):
        add("name-spec", WARN,
            f"`{sk.name}` violates the Agent Skills spec (1-64 chars, lowercase "
            f"alphanumerics and single hyphens)",
            "the spec makes this a hard requirement; claude.ai upload rejects it")
    if sk.name in GENERIC_NAMES:
        add("name-generic", WARN, f"`{sk.name}` is on the official avoid-list",
            "helper/utils/tools/documents/data/files say nothing about when to "
            "trigger — the docs list them verbatim as names to avoid")

    if len(d) > DESC_MAX:
        add("description-too-long", WARN,
            f"description is {len(d)} chars (spec cap {DESC_MAX})",
            "claude.ai enforces the cap as a hard error; Claude Code truncates "
            "the listing instead, so the tail quietly stops matching")
    when_to_use = str(sk.frontmatter.get("when_to_use", ""))
    if len(d) + len(when_to_use) > LISTING_MAX:
        add("description-truncated", WARN,
            f"description + when_to_use is {len(d) + len(when_to_use)} chars — Claude Code "
            f"cuts the skill listing at {LISTING_MAX}",
            "everything past the cutoff is invisible to the trigger decision; put "
            "the key use case first and trim")
    if XML_TAG.search(d):
        add("description-xml-tags", WARN, "description contains an XML/HTML tag",
            "the docs forbid XML tags in name and description outright")

    comp = sk.frontmatter.get("compatibility")
    if comp is not None and len(str(comp)) > 500:
        add("compatibility-too-long", WARN,
            f"compatibility is {len(str(comp))} chars (cap 500)")

    unknown = sorted(set(sk.frontmatter) - CODE_KEYS)
    if unknown:
        add("frontmatter-unknown-key", WARN,
            f"frontmatter key(s) no runtime documents: {', '.join(f'`{k}`' for k in unknown[:5])}",
            "neither the Agent Skills spec nor Claude Code knows these — usually a "
            "typo, and a typo'd field is silently dropped. (Spec-portability note: "
            "claude.ai upload hard-fails on ANY key outside the spec's six, "
            "including Claude Code's own extensions)")

    # --- body budgets (docs 500 lines / <5k tokens; Copilot documents ~1k decay) --
    if nlines > BODY_HARD_LINES:
        add("body-far-too-long", ERROR,
            f"body is {nlines} lines — past every vendor's documented ceiling",
            "Anthropic and Cursor guide 500; Copilot documents quality decay past "
            "~1,000. This needs progressive disclosure, not trimming")
    est_tokens = len(body) // 4
    if est_tokens > BODY_TOKEN_BUDGET:
        add("body-token-budget", WARN,
            f"body is ~{est_tokens} tokens (chars/4) — the progressive-disclosure "
            f"budget for a loaded skill is <{BODY_TOKEN_BUDGET}",
            "the whole body enters context on every trigger; move detail into "
            "references/ that load only when needed")

    if (m0 := VAGUE_EXHORT.search(prose)):
        add("vague-exhortation", INFO,
            f"body contains {m0.group(0)!r} — exhortation, not instruction",
            "vague quality demands add noise without changing behaviour; state a "
            "measurable constraint instead",
            sk.body_line0 + prose[:m0.start()].count("\n"))
    if (dm := DRIVE_PATH.search(prose)):
        add("windows-path", INFO, f"body contains a drive-letter path ({dm.group(0)!r}…)",
            "skill paths must use forward slashes — backslash paths break on Unix",
            sk.body_line0 + prose[:dm.start()].count("\n"))

    # --- bundled resources -------------------------------------------------
    # A link inside an inline code span is a *template being shown*, not a link
    # being made (`- [Title](file.md) — hook`). Blank spans for this scan only —
    # absence-based rules (learning-no-location etc.) still need inline-code
    # content. FP found twice in one pass on memory-hygiene, 2026-08-18.
    link_prose = INLINE_CODE.sub(lambda m: " " * len(m.group(0)), prose)
    for lm in MD_LINK.finditer(link_prose):
        target = lm.group(1).split("#")[0].strip()
        if not target or "://" in target or target.startswith(("mailto:", "<")):
            continue
        if any(ch in target for ch in "*{}$") or target.startswith("~"):
            continue                                   # a glob or a placeholder
        if not (sk.dir / target).exists() and not (sk.dir.parent / target).exists():
            add("broken-reference", WARN, f"links to `{target}`, which does not exist",
                "a reference the model cannot open is worse than no reference",
                sk.body_line0 + prose[:lm.start()].count("\n"))

    # One level deep: a reference file that links onward to a local .md not
    # itself linked from SKILL.md creates a chain Claude reads only partially.
    root_links = {Path(lm.group(1).split("#")[0].strip()).name
                  for lm in MD_LINK.finditer(prose)}
    chained: list[str] = []
    for ref in sorted(sk.dir.rglob("*.md")):
        if ref == sk.path or "node_modules" in ref.parts:
            continue
        rtext = strip_fences(ref.read_text(encoding="utf-8", errors="replace"))
        for lm in MD_LINK.finditer(rtext):
            tgt = lm.group(1).split("#")[0].strip()
            if not tgt or "://" in tgt or not tgt.endswith(".md"):
                continue
            if Path(tgt).name not in root_links and Path(tgt).name != sk.path.name:
                chained.append(str(ref.relative_to(sk.dir)))
                break
    if chained:
        # One finding per SKILL, not per file: cloudflare's doc-tree skill has
        # ~100 interlinked references, and 174 rows for one design decision is
        # a flood that buries every other signal in the run.
        add("reference-chain", WARN,
            f"{len(chained)} reference file(s) link onward to local .md files that "
            f"SKILL.md never links directly (e.g. {', '.join(chained[:3])})",
            "references should stay one level deep — nested chains get "
            "partially read and the tail is silently lost")

    scripts_dir = sk.dir / "scripts"
    if scripts_dir.is_dir():
        unref = [sc.name for sc in sorted(scripts_dir.iterdir())
                 if sc.is_file() and sc.name not in sk.text]
        if unref:
            add("script-unreferenced", WARN,
                f"{len(unref)} script(s) ship with the skill but SKILL.md never mentions "
                f"them: {', '.join(unref[:4])}{'…' if len(unref) > 4 else ''}",
                "a bundled script must say whether Claude runs it or reads it; one "
                "it never names is dead weight in the package")

    for ref in sorted(sk.dir.glob("references/*.md")):
        rl = len(ref.read_text(encoding="utf-8", errors="replace").splitlines())
        if rl > REF_TOC_LINES and not SEEN_TOC.search(ref.read_text(encoding="utf-8", errors="replace")):
            add("reference-no-toc", INFO,
                f"references/{ref.name} is {rl} lines with no table of contents",
                "a long reference without a map forces a full read to find one section")
    return out


# --------------------------------------------------------------- agent files

# Agent definitions (agents/*.md) share the frontmatter mechanics of skills but
# not the schema. The check that pays for this whole section: `allowed-tools:`
# is the SLASH-COMMAND field. In an agent it is silently ignored and the agent
# runs with the full tool set — which is how a plugin shipped three "read-only"
# agents that could write, edit, and push. Found 2026-08-18 in review-agents.
AGENT_TOOL_NAMES = {
    "Read", "Write", "Edit", "Bash", "Grep", "Glob", "WebFetch", "WebSearch",
    "Task", "NotebookEdit", "TodoWrite", "AskUserQuestion", "Skill",
}


def check_agent(sk: Skill) -> list[Finding]:
    out: list[Finding] = []
    add = lambda r, lv, m, h="", ln=0: out.append(Finding(sk.label, r, lv, m, h, ln))

    if sk.fm_error:
        add("frontmatter-invalid", ERROR, sk.fm_error,
            "an agent with unparseable frontmatter cannot be selected at all", 1)
        return out
    if not sk.name:
        add("name-missing", ERROR, "frontmatter has no `name`", ln=1)
    elif sk.name != sk.path.stem:
        add("name-mismatch", ERROR,
            f"frontmatter name `{sk.name}` does not match file `{sk.path.stem}.md`",
            "delegation addresses the agent by name; a mismatch makes it unreachable", 1)
    if not sk.description:
        add("description-missing", ERROR, "frontmatter has no `description`",
            "the description is what decides whether this agent is delegated to", 1)
    elif not TRIGGER.search(sk.description):
        add("description-no-trigger", WARN,
            "description never says WHEN to use the agent",
            'the conductor picks agents by description — say "Use this agent when …"')

    if "allowed-tools" in sk.frontmatter:
        add("agent-wrong-tools-field", ERROR,
            "`allowed-tools:` is the slash-command field — agents use `tools:`",
            "an unrecognized field is silently ignored, so the agent runs with the "
            "FULL tool set; any read-only or scoped claim built on it is false", 1)

    tools_raw = str(sk.frontmatter.get("tools", ""))
    if tools_raw:
        unknown = [t.strip() for t in tools_raw.split(",")
                   if t.strip() and t.strip().split("(")[0] not in AGENT_TOOL_NAMES
                   and not t.strip().startswith("mcp__")]
        if unknown:
            add("agent-unknown-tool", WARN,
                f"tools lists {', '.join(f'`{u}`' for u in unknown[:4])} — not a known tool name",
                "a misspelled tool grants nothing and fails silently at delegation time")
    return out


# ---------------------------------------------------------------- skill types
# Signal-based, multi-label: an orchestrator with a learnings log is both, and
# each label switches on its own extra checks. The taxonomy grounds in
# obra/superpowers writing-skills (Technique/Pattern/Reference) extended with
# the shapes real marketplaces ship: workflows, orchestrators, self-learning
# skills, scripted skills. A skill with no labels is a plain technique/pattern
# skill and pays nothing for the machinery.
STEP_HEADING = re.compile(r"^#{2,4}\s*(?:step|phase)\s+(\d+)", re.I | re.M)
ORCH_SIGNALS = re.compile(
    r"\b(subagents?|task tool|fan[- ]?outs?|dispatch(?:ing)?(?: an?)? agents?"
    r"|parallel(?: research| review)? agents?|rosters?|panel of|coverage roles"
    r"|relay(?:s|ed)?(?: the)? roles)\b", re.I)
LEARN_SIGNALS = re.compile(
    r"\b(self[- ](?:improving|learning|evolving)|learnings? log|misses log"
    r"|learned[- ]rules|learning loop|graduat\w+ (?:to|into) (?:mastered|core|conventions)"
    r"|append(?:ing)? (?:a |an |the )?(?:dated |new )?(?:entry|line|learning|miss)"
    r"|add (?:it |this )?to the learnings|decisions & learnings"
    r"|add(?:s)? a dated (?:line|entry)|checklist grows)\b", re.I)
SELF_APPEND = re.compile(
    r"\bappend(?:ing)?\b[^.\n]{0,80}\b(below|at the bottom|to this (?:file|skill)"
    r"|to the (?:learnings?|misses) log)\b", re.I)
IRREVERSIBLE_CMD = re.compile(
    r"^\s*(?:git push|kubectl (?:apply|delete)|helm (?:install|upgrade|uninstall)"
    r"|terraform apply|npm publish|mvn deploy|gh release)", re.I | re.M)
GATE_WORDS = re.compile(
    r"\b(confirm|confirmation|approval|approve|asks? the user|user[- ]gated"
    r"|explicit(?:ly)? (?:go-ahead|consent|confirmation)|dry[- ]run first"
    r"|stops? for|sign[- ]?off)\b", re.I)
STOP_WORDS = re.compile(
    r"\b(round cap|cap of|at most|limit(?:ed)? to|stopping (?:rule|condition)"
    r"|max(?:imum)? (?:rounds?|attempts?|agents?)|budget|converge)\b", re.I)
CONTRACT_WORDS = re.compile(
    r"\b(output contract|report (?:format|structure|template)|schema"
    r"|structured (?:output|findings)|return format)\b|^#{2,3}\s*(?:Output|Report)\b",
    re.I | re.M)


def classify(sk: Skill, prose: str) -> list[str]:
    types: list[str] = []
    body = sk.body
    lines = body.splitlines() or [""]
    if len(STEP_HEADING.findall(body)) >= 3:
        types.append("workflow")
    if len({m.group(1).lower() for m in ORCH_SIGNALS.finditer(prose)}) >= 2:
        types.append("orchestrator")
    if LEARN_SIGNALS.search(prose) or LEARN_SIGNALS.search(sk.description):
        types.append("learning")
    ref_lines = sum(1 for l in lines if l.lstrip().startswith(("|", "```", "    ")))
    if len(lines) > 60 and ref_lines / len(lines) > 0.5:
        types.append("reference")
    sibs = [q for q in sk.dir.iterdir()
            if q.is_file() and q.suffix in (".py", ".sh", ".js")] if sk.dir.is_dir() else []
    if (sk.dir / "scripts").is_dir() or len(sibs) >= 2:
        types.append("scripted")
    return types


def in_plugin(sk: Skill) -> bool:
    """Installed plugins are versioned artifacts distributed via marketplaces —
    runtime state written inside one is lost on update."""
    for up in (sk.dir.parent, sk.dir.parent.parent, sk.dir.parent.parent.parent):
        if (up / ".claude-plugin" / "plugin.json").is_file():
            return True
    return False


def check_typed(sk: Skill, types: list[str], prose: str) -> list[Finding]:
    out: list[Finding] = []
    add = lambda r, lv, m, h="": out.append(Finding(sk.label, r, lv, m, h))

    if "workflow" in types:
        nums = sorted({int(n) for n in STEP_HEADING.findall(sk.body)})
        # Only a sequence that STARTS at 1 claims to be complete. Sections like
        # "Step 2 / Step 3 / Step 6" under a full numbered flow list are
        # deep-dives into selected steps, not a broken ladder — adapt-workflow
        # does exactly this and was the rule's first false positive.
        if nums and nums[0] == 1 and nums != list(range(1, len(nums) + 1)):
            add("workflow-step-gap", WARN,
                f"step numbering is {nums} — not contiguous",
                "a gap usually means a step was deleted without renumbering; "
                "the sequence reads as broken")
        if IRREVERSIBLE_CMD.search(sk.body) and not GATE_WORDS.search(prose):
            add("workflow-no-gate", INFO,
                "the workflow runs irreversible commands (push/deploy/publish) "
                "and never mentions a confirmation gate",
                "a procedure that never says when to stop and ask will "
                "eventually ship something unintended")

    if "orchestrator" in types:
        if not CONTRACT_WORDS.search(sk.body):
            add("orchestrator-no-contract", INFO,
                "fans out agents but never states an output contract",
                "without a shared output shape each agent invents its own and "
                "the merge becomes guesswork")
        if not STOP_WORDS.search(prose):
            add("orchestrator-no-stop", INFO,
                "fans out or loops without a cap or stopping rule",
                "an orchestrator with no stated bound runs until something "
                "external stops it")

    if "learning" in types:
        # Location can legitimately live in the description ("append new gotchas
        # to the Learnings log each run") — classification reads it, so this must.
        text = prose + "\n" + sk.description
        consuming_repo_target = "claude.md" in text.lower() or ".claude/" in text
        if in_plugin(sk) and SELF_APPEND.search(text) and not consuming_repo_target:
            add("learning-writes-to-plugin", WARN,
                "a self-improving skill inside a plugin instructs appending to "
                "itself or a bundled log",
                "an installed plugin is a versioned artifact — state written "
                "inside it is overwritten on update. Learned state belongs in "
                "the consuming repo, e.g. .claude/<skill>/")
        elif not SELF_APPEND.search(text) and not re.search(
                r"\.claude/|~/\.|memory/|log\.md|\.json\b", text):
            add("learning-no-location", INFO,
                "describes a learning loop but never names where learnings live",
                "a loop without a stated location gets a different answer every "
                "session, and the learnings scatter")

    if "reference" in types and len(sk.body.splitlines()) > 100 \
            and not SEEN_TOC.search(sk.body):
        add("reference-skill-no-toc", INFO,
            "a reference-type skill over 100 lines with no table of contents",
            "the stricter official 100-line TOC guidance targets exactly this "
            "shape — a partial read should still reveal the scope (see "
            "rule-sources conflict #3)")

    if "scripted" in types:
        flat = [q.name for q in sk.dir.iterdir()
                if q.is_file() and q.suffix in (".py", ".sh", ".js")
                and q.name not in sk.text]
        if flat:
            add("script-unreferenced", WARN,
                f"{len(flat)} executable file(s) ship beside SKILL.md that it "
                f"never mentions: {', '.join(sorted(flat)[:4])}",
                "a bundled script must say whether Claude runs it or reads it; "
                "one it never names is dead weight in the package")
    return out


# ------------------------------------------------------------- plugin surfaces
# code.claude.com/docs/en/hooks — the complete valid event list. An unknown
# event in hooks.json is silently dead: the hook never fires, no error shown.
HOOK_EVENTS = {
    "SessionStart", "Setup", "UserPromptSubmit", "UserPromptExpansion",
    "PreToolUse", "PermissionRequest", "PermissionDenied", "PostToolUse",
    "PostToolUseFailure", "PostToolBatch", "Notification", "MessageDisplay",
    "SubagentStart", "SubagentStop", "TaskCreated", "TaskCompleted", "Stop",
    "StopFailure", "TeammateIdle", "InstructionsLoaded", "ConfigChange",
    "CwdChanged", "DirectoryAdded", "FileChanged", "WorktreeCreate",
    "WorktreeRemove", "PreCompact", "PostCompact", "Elicitation",
    "ElicitationResult", "SessionEnd",
}
PLUGIN_ROOT_VAR = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\s\"']+)")


def check_hooks(path: Path) -> list[Finding]:
    """hooks/hooks.json: events must be real, command targets must exist."""
    label = f"{path.parent.parent.name}/hooks.json"
    out: list[Finding] = []
    add = lambda r, lv, m, h="": out.append(Finding(label, r, lv, m, h))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        add("hooks-invalid-json", ERROR, f"hooks.json does not parse: {exc}",
            "a broken hooks file means every hook in it is silently dead")
        return out
    plug = path.parent.parent
    for event, groups in (data.get("hooks") or {}).items():
        if event not in HOOK_EVENTS:
            add("hooks-unknown-event", ERROR,
                f"`{event}` is not a Claude Code hook event",
                "an unknown event name never fires and no error is shown — the "
                "hook is silently dead (see the documented event list)")
        for g in groups if isinstance(groups, list) else []:
            for hk in g.get("hooks", []):
                for m in PLUGIN_ROOT_VAR.finditer(str(hk.get("command", ""))):
                    if not (plug / m.group(1)).exists():
                        add("hooks-missing-target", ERROR,
                            f"{event} hook runs `{m.group(1)}`, which does not "
                            f"exist in the plugin",
                            "the hook will fail on every fire")
    return out


def check_plugin_root(root: Path) -> list[Finding]:
    """Plugin-level structure. The docs call one of these out verbatim as a
    'Common mistake': components inside .claude-plugin/ are not loaded."""
    label = f"{root.name}/(plugin)"
    out: list[Finding] = []
    add = lambda r, lv, m, h="": out.append(Finding(label, r, lv, m, h))
    for comp in ("commands", "agents", "skills", "hooks"):
        if (root / ".claude-plugin" / comp).is_dir():
            add("plugin-component-misplaced", ERROR,
                f"`{comp}/` sits inside .claude-plugin/ — Claude Code will not load it",
                "only plugin.json goes in .claude-plugin/; every component "
                "directory belongs at the plugin root")
    if (root / "commands").is_dir():
        add("plugin-commands-dir", INFO,
            "ships a commands/ directory (flat skill files)",
            "the docs' structure table: 'Skills as flat Markdown files. Use "
            "skills/ for new plugins' — existing ones keep working")
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

# ------------------------------------------------- discovery (the skills CLI)
#
# `npx skills add <owner>/<repo>` is how a skill reaches the 30-odd agents that
# are not Claude Code, and its install telemetry is the only way onto skills.sh.
# It finds skills by walking a fixed set of directories, and every way of
# missing one is silent: no error, the skill is simply not in the list.
#
# This is a port of `discoverSkills` (vercel-labs/skills v1.7.0, src/skills.ts
# and src/plugin-manifest.ts) — the walk itself, not a summary of it, so the
# linter and the CLI cannot disagree about what is reachable.

CLI_SKIP_DIRS = {"node_modules", ".git", "dist", "build", "__pycache__"}
CLI_CONTAINER_DEPTH = 3
CLI_AGENT_DIRS = [
    ".agents/skills", ".claude/skills", ".cline/skills", ".codebuddy/skills",
    ".codex/skills", ".commandcode/skills", ".continue/skills", ".factory/skills",
    ".github/skills", ".goose/skills", ".grok/skills", ".iflow/skills",
    ".junie/skills", ".kilo/skills", ".kilocode/skills", ".kimchi/skills",
    ".kiro/skills", ".minimax/skills", ".mux/skills", ".neovate/skills",
    ".opencode/skills", ".openhands/skills", ".pi/skills", ".posit/assistant/skills",
    ".qoder/skills", ".roo/skills", ".trae/skills", ".windsurf/skills",
    ".zcode/skills", ".zencoder/skills",
]


def cli_install_name(name: str) -> str:
    """`sanitizeName` (installer.ts): the directory a skill is installed into."""
    out = re.sub(r"[^a-z0-9._]+", "-", name.lower())
    return re.sub(r"^[.\-]+|[.\-]+$", "", out)[:255] or "unnamed-skill"


def cli_skip_reason(sk: Skill) -> str:
    """Why `parseSkillMd` would return null for this file, or ""."""
    if sk.fm_error:
        return "its frontmatter is not valid YAML"
    ex = sk.fm_extra
    for k in ("name", "description"):
        raw = sk.frontmatter.get(k, "")
        if not raw:
            return f"it has no `{k}`"
        if k in ex.get("collection", ()) or (
                k not in ex.get("quoted", ()) and YAML_NONSTR.match(raw)):
            return f"its `{k}` is not a string"
    if ex.get("nested", {}).get("metadata", {}).get("internal", "").lower() == "true":
        return "it is marked `metadata.internal`"
    return ""


def _inside(p: Path, base: Path) -> bool:
    try:
        p.resolve().relative_to(base.resolve())
        return True
    except (ValueError, OSError):
        return False


def _subdirs(d: Path) -> list[Path]:
    try:
        return sorted(c for c in d.iterdir() if c.is_dir())
    except OSError:
        return []


def cli_plugin_bases(root: Path) -> tuple[list[Path], dict[str, str]]:
    """Plugin directories the CLI will look inside, plus — for the entries it
    will NOT — a `name → reason` map. Mirrors getPluginSkillPaths."""
    bases: list[Path] = []
    skipped: dict[str, str] = {}
    try:
        mk = json.loads((root / ".claude-plugin" / "marketplace.json").read_text("utf-8"))
    except (OSError, ValueError):
        return bases, skipped
    if not isinstance(mk, dict):
        return bases, skipped
    meta = mk.get("metadata") if isinstance(mk.get("metadata"), dict) else {}
    proot = meta.get("pluginRoot")
    root_ok = proot is None or (isinstance(proot, str) and proot.startswith("./"))
    for pl in mk.get("plugins") or []:
        if not isinstance(pl, dict):
            continue
        name, src = str(pl.get("name", "?")), pl.get("source")
        if not root_ok:
            skipped[name] = f"`metadata.pluginRoot` is `{proot}`, which does not start with `./`"
        elif src is not None and not isinstance(src, str):
            continue                   # a remote plugin: its skills live in another repo
        elif isinstance(src, str) and not src.startswith("./"):
            skipped[name] = f"its marketplace `source` is `{src}`, which does not start with `./`"
        else:
            base = root / (proot or "") / (src or "")
            if _inside(base, root):
                bases.append(base)
            else:
                skipped[name] = f"its marketplace `source` `{src}` points outside the repo"
    return bases, skipped


def cli_discover(root: Path, loadable) -> list[Path]:
    """Skill directories `npx skills add` reaches from `root`, in visit order.

    `loadable(dir)` says whether the CLI would accept that directory's
    SKILL.md; it matters because the walk only falls back to a full recursive
    search when it has found NO acceptable skill."""
    seen: list[Path] = []
    good = 0

    def take(d: Path) -> bool:
        nonlocal good
        if not (d / "SKILL.md").is_file():
            return False
        if d not in seen:
            seen.append(d)
            good += bool(loadable(d))
        return True

    if (root / "SKILL.md").is_file():
        take(root)
        if good:
            return seen                # a root skill is the whole answer, by design

    def walk(d: Path, max_depth: int, depth: int = 1) -> None:
        for child in _subdirs(d):
            if take(child) or depth >= max_depth or child.name in CLI_SKIP_DIRS:
                continue               # nothing below a skill is ever visited
            walk(child, max_depth, depth + 1)

    walk(root, 1)
    for rel in ["skills", "skills/.curated", "skills/.experimental", "skills/.system",
                *CLI_AGENT_DIRS]:
        walk(root / rel, CLI_CONTAINER_DEPTH)

    bases, _ = cli_plugin_bases(root)
    declared: list[Path] = []
    try:
        mk = json.loads((root / ".claude-plugin" / "marketplace.json").read_text("utf-8"))
        entries = [p for p in (mk.get("plugins") or []) if isinstance(p, dict)]
    except (OSError, ValueError, AttributeError):
        entries = []
    for base in bases:
        for pl in entries:
            for sp in pl.get("skills") or []:
                if isinstance(sp, str) and sp.startswith("./") and _inside(base / sp, root) \
                        and (base / sp).exists():
                    declared.append((base / sp).parent)
        declared.append(base / "skills")
    try:
        pj = json.loads((root / ".claude-plugin" / "plugin.json").read_text("utf-8"))
        for sp in (pj.get("skills") or []) if isinstance(pj, dict) else []:
            if isinstance(sp, str) and sp.startswith("./") and _inside(root / sp, root):
                declared.append((root / sp).parent)
        declared.append(root / "skills")
    except (OSError, ValueError):
        pass
    for d in declared:
        walk(d, 1)

    if not good:                       # the only time the CLI searches everywhere
        def deep(d: Path, depth: int = 0) -> None:
            if depth > 5:
                return
            take(d)
            for child in _subdirs(d):
                if child.name not in CLI_SKIP_DIRS:
                    deep(child, depth + 1)
        deep(root)
    return seen


def distribution_root(start: Path) -> Path | None:
    """The repo a path belongs to, IF that repo publishes skills. A project
    that merely keeps a few skills for itself is not a catalog, and holding
    it to a catalog's rules would be noise."""
    start = start.resolve()
    for d in [start, *start.parents]:
        cp = d / ".claude-plugin"
        if (cp / "marketplace.json").is_file() or (d / "skills.sh.json").is_file():
            return d
        if (d / ".git").exists():
            return d if (cp / "plugin.json").is_file() else None
    return None


def check_discovery(root: Path, scanned: list[Path]) -> list[Finding]:
    """Collection-level: what the skills CLI will and will not list for `root`."""
    out: list[Finding] = []
    cache: dict[Path, Skill] = {}

    def sk_at(d: Path) -> Skill:
        if d not in cache:
            cache[d] = load_skill(d / "SKILL.md")
        return cache[d]

    reached = cli_discover(root, lambda d: not cli_skip_reason(sk_at(d)))
    reached_set = set(reached)
    bases, skipped = cli_plugin_bases(root)
    base_set = {b.resolve() for b in bases}
    shadow = (root / "SKILL.md").is_file() and reached == [root]

    # 1. A shipped skill the CLI never visits.
    hidden = 0
    for f in scanned:
        d = f.resolve().parent
        if d in reached_set or not _inside(d, root):
            continue
        plugin = next((a for a in d.parents if (a / ".claude-plugin" / "plugin.json").is_file()
                       and _inside(a, root)), None)
        if plugin is None and _inside(d, root / "skills"):
            plugin = root              # a plain `skills/` catalog at the repo root
        if plugin is None or not _inside(d, plugin / "skills"):
            continue                   # a fixture or an example, not a shipped skill
        if shadow:
            hidden += 1                # one cause, one finding — see below
            continue
        if plugin.resolve() not in base_set and plugin.resolve() != root.resolve():
            try:
                pname = json.loads((plugin / ".claude-plugin" / "plugin.json")
                                   .read_text("utf-8")).get("name", plugin.name)
            except (OSError, ValueError, AttributeError):
                pname = plugin.name
            why = skipped.get(pname) or (
                f"plugin `{pname}` has no entry in .claude-plugin/marketplace.json, "
                f"and the CLI only looks inside listed plugins")
        else:
            rel = d.relative_to((plugin / "skills").resolve())
            holder = next((a for a in d.parents if a in reached_set), None)
            why = (f"it sits inside another skill (`{holder.name}`), and the CLI never "
                   f"looks below a SKILL.md" if holder else
                   f"it is {len(rel.parts)} levels below `skills/`, and the CLI walks "
                   f"the repo's own `skills/` {CLI_CONTAINER_DEPTH} levels deep"
                   if plugin.resolve() == root.resolve() else
                   f"it is {len(rel.parts)} levels below `skills/` and the CLI reads a "
                   f"plugin's `skills/` one level deep — move it up, or name it in the "
                   f"plugin's marketplace `skills` array")
        out.append(Finding(sk_at(d).label, "skill-undiscoverable", WARN,
                           f"`npx skills add` will not list this skill: {why}",
                           "nothing reports the miss — the skill is just absent from the "
                           "list, and from skills.sh, which is built from CLI installs"))

    if hidden:
        out.append(Finding(
            "(collection)", "root-skill-shadows", WARN,
            f"the repo root has its own SKILL.md, so `npx skills add` lists that one "
            f"skill and stops — {hidden} other skill(s) here are never offered",
            "a root SKILL.md means \"this repo IS a skill\" to the CLI; only "
            "`--full-depth` looks further. Move it into `skills/<name>/`"))

    # 2. Two reachable skills the CLI cannot tell apart.
    by_name: dict[str, list[Path]] = {}
    by_dir: dict[str, list[Path]] = {}
    for d in reached:
        sk = sk_at(d)
        if cli_skip_reason(sk):
            continue
        by_name.setdefault(sk.name, []).append(d)
        by_dir.setdefault(cli_install_name(sk.name), []).append(d)
    rel = lambda d: str(d.relative_to(root)) if _inside(d, root) else str(d)
    for name, dirs in sorted(by_name.items()):
        if len(dirs) > 1:
            out.append(Finding(
                "(collection)", "duplicate-skill-name", WARN,
                f"{len(dirs)} skills are named `{name}`: {', '.join(rel(d) for d in dirs)}",
                "the skills CLI keeps whichever it reads first and drops the rest "
                "without a word; Claude Code namespaces by plugin, so this only shows "
                "up on install"))
    for slug, dirs in sorted(by_dir.items()):
        names = sorted({sk_at(d).name for d in dirs})
        if len(names) > 1:
            out.append(Finding(
                "(collection)", "duplicate-skill-name", WARN,
                f"{', '.join(f'`{n}`' for n in names)} all install into the directory `{slug}`",
                "the CLI lowercases a name and turns every run of other characters "
                "into `-`; the later install overwrites the earlier one"))

    # 3. Repo-local skills published along with the catalog.
    if (root / ".claude-plugin" / "marketplace.json").is_file():
        local = [d for d in reached
                 if any(_inside(d, root / a) for a in CLI_AGENT_DIRS)
                 and not cli_skip_reason(sk_at(d))]
        if local:
            out.append(Finding(
                "(collection)", "agent-dir-skill-listed", INFO,
                f"{len(local)} skill(s) under an agent config dir are listed by "
                f"`npx skills add` next to the catalog: "
                f"{', '.join(rel(d) for d in local[:4])}{' …' if len(local) > 4 else ''}",
                "the CLI searches `.claude/skills`, `.agents/skills` and 28 similar "
                "dirs in every repo — fine if these are meant to ship; set "
                "`metadata.internal: true` on any that are not"))

    out += check_skills_sh(root, {sk_at(d).name for d in reached
                                  if not cli_skip_reason(sk_at(d))})
    return out


def _slug(s: str) -> str:
    return re.sub(r"[\s_]+", "-", s.strip().lower())


def check_skills_sh(root: Path, names: set[str]) -> list[Finding]:
    """`skills.sh.json` groups a repo's page on skills.sh. An invalid file is
    not rejected — the page silently falls back to the flat default list."""
    f = root / "skills.sh.json"
    if not f.is_file():
        return []
    bad = lambda m: [Finding("skills.sh.json", "skills-sh-invalid", WARN, m,
                             "skills.sh ignores an invalid file and shows the default "
                             "list, so the grouping never appears and nothing says why")]
    try:
        cfg = json.loads(f.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        return bad(f"not valid JSON: {exc}")
    if not isinstance(cfg, dict):
        return bad("the top level must be an object")
    problems: list[str] = []
    extra = sorted(set(cfg) - {"$schema", "schema", "notGrouped", "groupings"})
    if extra:
        problems.append(f"unknown key(s) {', '.join(f'`{k}`' for k in extra)}")
    if "notGrouped" in cfg and cfg["notGrouped"] not in ("top", "bottom"):
        problems.append('`notGrouped` must be "top" or "bottom"')
    groups = cfg.get("groupings")
    if not isinstance(groups, list) or not 1 <= len(groups) <= 50:
        problems.append("`groupings` is required and takes 1–50 groups")
        groups = []
    listed: dict[str, str] = {}
    out: list[Finding] = []
    for i, g in enumerate(groups, 1):
        if not isinstance(g, dict):
            problems.append(f"group {i} is not an object")
            continue
        title, skills = g.get("title"), g.get("skills")
        tag = f"group {i}" + (f" (`{title}`)" if isinstance(title, str) and title else "")
        junk = sorted(set(g) - {"title", "description", "skills"})
        if junk:
            problems.append(f"{tag}: unknown key(s) {', '.join(f'`{k}`' for k in junk)}")
        if not isinstance(title, str) or not 1 <= len(title) <= 120:
            problems.append(f"{tag}: `title` must be 1–120 characters")
        if "description" in g and (not isinstance(g["description"], str)
                                   or len(g["description"]) > 500):
            problems.append(f"{tag}: `description` must be text of at most 500 characters")
        if not isinstance(skills, list) or not 1 <= len(skills) <= 500 or not all(
                isinstance(s, str) and 1 <= len(s) <= 120 for s in skills):
            problems.append(f"{tag}: `skills` takes 1–500 names of 1–120 characters")
            continue
        for s in skills:
            if _slug(s) in listed and listed[_slug(s)] != tag:
                out.append(Finding(
                    "skills.sh.json", "skills-sh-duplicate", INFO,
                    f"`{s}` is in {listed[_slug(s)]} and {tag}",
                    "a skill appears once, in the first group that names it"))
            listed.setdefault(_slug(s), tag)
    if problems:
        return bad("; ".join(problems[:6]) + (" …" if len(problems) > 6 else ""))
    known = {_slug(n) for n in names}
    ghosts = sorted(s for s in listed if s not in known)
    if ghosts and known:
        out.append(Finding(
            "skills.sh.json", "skills-sh-unknown-skill", WARN,
            f"{len(ghosts)} grouped name(s) match no skill the CLI can list: "
            f"{', '.join(f'`{g}`' for g in ghosts[:6])}{' …' if len(ghosts) > 6 else ''}",
            "names that match nothing are ignored without an error — usually a "
            "rename the file did not follow"))
    return out


def load_skill(p: Path) -> Skill:
    text = p.read_text(encoding="utf-8", errors="replace")
    extra: dict = {}
    fm, body, line0, err = parse_frontmatter(text, extra)
    return Skill(path=p, dir=p.parent, name=str(fm.get("name", "")),
                 description=" ".join(str(fm.get("description", "")).split()),
                 frontmatter=fm, fm_error=err, body=body, body_line0=line0, text=text,
                 fm_extra=extra)


def _is_agent_dir(d: Path) -> bool:
    """Only two homes make an agents/ dir hold Claude Code agent DEFINITIONS:
    a plugin root (sibling .claude-plugin/) or a .claude/ config dir. An
    `agents/` folder nested inside a skill is that skill's own reference
    material — skill-creator ships grader.md/comparator.md instruction docs
    there, deliberately frontmatter-free, and linting them as agents produced
    three false ERRORs."""
    parent = d.parent
    return (parent / ".claude-plugin").is_dir() or parent.name == ".claude"


def discover(paths: list[str]) -> tuple[list[Path], list[Path]]:
    """Returns (skills, agents). An agent file is any .md directly inside a
    plugin-level `agents/` directory — role.md files, references, and a
    skill's own agents/ instruction docs are never agents."""
    skills: list[Path] = []
    agents: list[Path] = []
    hooks: list[Path] = []
    plugin_roots: list[Path] = []
    commands: list[Path] = []
    for raw in paths or ["."]:
        p = Path(raw)
        if p.is_file() and p.name == "SKILL.md":
            skills.append(p)
        elif (p.is_file() and p.parent.name == "agents" and p.suffix == ".md"
              and _is_agent_dir(p.parent)):
            agents.append(p)
        else:
            root = p if p.is_dir() else p.parent
            if (p / "SKILL.md").is_file():
                skills.append(p / "SKILL.md")
            for q in root.rglob("*.md"):
                if any(part in {"node_modules", ".git"} for part in q.parts):
                    continue
                if q.name == "SKILL.md" and (p / "SKILL.md") not in skills:
                    skills.append(q)
                elif q.parent.name == "agents" and _is_agent_dir(q.parent):
                    agents.append(q)
                elif q.parent.name == "commands":
                    commands.append(q)
            for q in root.rglob("hooks/hooks.json"):
                if not any(part in {"node_modules", ".git"} for part in q.parts):
                    hooks.append(q)
            for q in root.rglob(".claude-plugin/plugin.json"):
                if not any(part in {"node_modules", ".git"} for part in q.parts):
                    plugin_roots.append(q.parent.parent)
    return (sorted(set(skills)), sorted(set(agents)),
            sorted(set(commands)), sorted(set(hooks)), sorted(set(plugin_roots)))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="*", help="SKILL.md files, skill dirs, or a tree to walk")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    ap.add_argument("--rules", default=".claude/skill-linter/learned-rules.json",
                    help="learned-rule file (default: %(default)s)")
    ap.add_argument("--only", help="comma-separated rule ids to report")
    args = ap.parse_args(argv)

    skill_files, agent_files, command_files, hook_files, plugin_roots = discover(args.paths)
    files = skill_files + agent_files + command_files
    if not files:
        print("no SKILL.md or agents/*.md found", file=sys.stderr)
        return 2

    learned = load_learned(Path(args.rules))
    findings: list[Finding] = []
    skill_types: dict[str, list[str]] = {}
    for f in skill_files:
        sk = load_skill(f)
        prose = strip_fences(sk.body)
        types = classify(sk, prose)
        if types:
            skill_types[sk.label] = types
        findings += check(sk) + check_typed(sk, types, prose) + apply_learned(sk, learned)
    for f in agent_files:
        findings += check_agent(load_skill(f))
    for f in command_files:
        # Commands are skills with a flat layout (docs: "merged into skills").
        # The name comes from the filename, so name rules don't apply.
        sk = load_skill(f)
        # A command's primary invocation is BY NAME (/plugin:command), so the
        # trigger-description rules only matter when it is Claude-invoked
        # (user-invocable: false). Name rules never apply: the filename is the name.
        drop = {"name-missing", "name-mismatch", "name-format", "name-spec",
                "name-generic", "trigger-info-in-body", "body-thin"}
        if str(sk.frontmatter.get("user-invocable", "true")).lower() != "false":
            drop |= {"description-no-trigger", "description-no-phrases", "description-vague"}
        findings += [x for x in check(sk) if x.rule not in drop]
    for f in hook_files:
        findings += check_hooks(f)
    for r in plugin_roots:
        findings += check_plugin_root(r)

    # Collection budget: every installed skill's name+description shares one
    # ~15,000-char system-prompt allowance; skills past the cutoff never load.
    if len(skill_files) > 1:
        total = 0
        for f in skill_files:
            sk = load_skill(f)
            total += len(sk.name) + len(sk.description)
        if total > 15000:
            findings.append(Finding(
                "(collection)", "collection-desc-budget", WARN,
                f"name+description across {len(skill_files)} skills totals {total} chars — "
                f"the shared listing budget is ~15,000",
                "skills past the cutoff silently never trigger; trim the longest "
                "descriptions first"))

    # Discovery: only for a repo that publishes skills, and only when the run
    # covers a collection — linting one skill should not audit the catalog.
    if len(skill_files) > 1:
        roots = {distribution_root(Path(p)) for p in (args.paths or ["."])}
        for root in sorted(r for r in roots if r):
            findings += check_discovery(root, skill_files)

    if args.only:
        keep = {s.strip() for s in args.only.split(",")}
        findings = [f for f in findings if f.rule in keep]

    counts = {lv: sum(1 for f in findings if f.level == lv) for lv in LEVELS}

    if args.json:
        print(json.dumps({
            "skills": len(files), "counts": counts, "learned_rules": len(learned),
            "types": skill_types,
            "findings": [vars(f) for f in findings],
        }, indent=2))
    else:
        by_skill: dict[str, list[Finding]] = {}
        for f in findings:
            by_skill.setdefault(f.skill, []).append(f)
        mark = {ERROR: "✗", WARN: "!", INFO: "·"}
        for skill in sorted(by_skill):
            tag = f"  [{', '.join(skill_types[skill])}]" if skill in skill_types else ""
            print(f"\n  {skill}{tag}")
            for f in sorted(by_skill[skill], key=lambda x: LEVELS.index(x.level)):
                loc = f":{f.line}" if f.line else ""
                print(f"    {mark[f.level]} {f.rule}{loc} — {f.message}")
                if f.hint:
                    for i, ln in enumerate(_wrap(f.hint, 84)):
                        print(f"        {'→ ' if i == 0 else '  '}{ln}")
        clean = len(files) - len(by_skill)
        print(f"\n  {len(skill_files)} skills + {len(agent_files)} agents · {clean} clean · "
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
