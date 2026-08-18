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

    NESTED = "nested"          # `metadata:` with no value + indented children — valid YAML
    for raw in lines[1:end]:
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", raw)
        if m and not raw.startswith((" ", "\t")):
            flush()
            key, rest = m.group(1), m.group(2).strip()
            if rest in (">", "|", ">-", "|-", ">+", "|+"):
                buf, mode = [], (FOLDED if rest[0] == ">" else LITERAL)
            elif rest == "":
                # An empty value followed by indented `sub: val` lines is a real
                # nested mapping (antfu's skills: `metadata:` / `  author: …`).
                # The guard below is only for text scalars that grow a colon —
                # firing here called three perfectly valid skills broken.
                buf, mode = [], NESTED
            else:
                buf, mode = [rest], PLAIN
        elif key is not None:
            if mode is NESTED:
                continue               # children of a nested map: not our schema, skip
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
        if nums and nums != list(range(nums[0], nums[0] + len(nums))):
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
        consuming_repo_target = "claude.md" in prose.lower() or ".claude/" in prose
        if in_plugin(sk) and SELF_APPEND.search(prose) and not consuming_repo_target:
            add("learning-writes-to-plugin", WARN,
                "a self-improving skill inside a plugin instructs appending to "
                "itself or a bundled log",
                "an installed plugin is a versioned artifact — state written "
                "inside it is overwritten on update. Learned state belongs in "
                "the consuming repo, e.g. .claude/<skill>/")
        elif not SELF_APPEND.search(prose) and not re.search(
                r"\.claude/|~/\.|memory/|log\.md|\.json\b", prose):
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

def load_skill(p: Path) -> Skill:
    text = p.read_text(encoding="utf-8", errors="replace")
    fm, body, line0, err = parse_frontmatter(text)
    return Skill(path=p, dir=p.parent, name=str(fm.get("name", "")),
                 description=" ".join(str(fm.get("description", "")).split()),
                 frontmatter=fm, fm_error=err, body=body, body_line0=line0, text=text)


def discover(paths: list[str]) -> tuple[list[Path], list[Path]]:
    """Returns (skills, agents). An agent file is any .md directly inside an
    `agents/` directory — role.md files and references are never agents."""
    skills: list[Path] = []
    agents: list[Path] = []
    hooks: list[Path] = []
    plugin_roots: list[Path] = []
    commands: list[Path] = []
    for raw in paths or ["."]:
        p = Path(raw)
        if p.is_file() and p.name == "SKILL.md":
            skills.append(p)
        elif p.is_file() and p.parent.name == "agents" and p.suffix == ".md":
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
                elif q.parent.name == "agents":
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
