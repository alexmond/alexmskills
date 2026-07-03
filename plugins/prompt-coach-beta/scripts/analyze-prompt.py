#!/usr/bin/env python3
"""
prompt-coach — analyze the user's prompt against a tiered ruleset of prompt
best practices, nudge (or stay silent) based on config, and evolve as clean
runs accumulate.

Reads UserPromptSubmit JSON on stdin. Writes hook JSON on stdout to inject
context for Claude; writes a boxed nudge to stderr for the user (both
optional, controlled by config.nudge_style). Never blocks the prompt.

State model:
  - Global (`~/.claude/prompt-coach/state.json`): mastery ledger shared
    across every repo — rules graduate here after N clean runs.
  - Local  (`.claude/prompt-coach/state.json`):  per-repo overrides,
    reactivations, and a rolling log of nudges.

Config resolution (first wins):
  local .claude/prompt-coach/config.json  →  global ~/.claude/prompt-coach/config.json  →  defaults
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

# ---------------------------------------------------------------------------
# Paths + defaults
# ---------------------------------------------------------------------------

HOME = Path(os.path.expanduser("~"))
GLOBAL_DIR = HOME / ".claude" / "prompt-coach"
GLOBAL_STATE = GLOBAL_DIR / "state.json"
GLOBAL_CONFIG = GLOBAL_DIR / "config.json"

DEFAULT_CONFIG = {
    # nudge_style: one of —
    #   "both"     stderr box + Claude sees (default). Requires TUI to render hook stderr.
    #   "silent"   Claude sees, user doesn't. Good after you've internalized rules.
    #   "log-only" nothing external; every fire only recorded in log.md.
    #   "inline"   the nudge is instructed to Claude to render as the opening
    #              block of its response. Most visible — nudge lives in your
    #              transcript. Adds ~50 output tokens per fire.
    "nudge_style": "both",
    "graduation_threshold": 15,   # clean prompts in a row → mastered
    "cooldown_prompts": 5,        # min prompts between same-rule nudges
    "max_active_rules": 6,        # never nag on more than this many rules at once
                                  # (v0.12.0: raised 5→6 to fit the new L1 tier
                                  # with no-answer-shape included)
    "pause_until_prompt": 0,      # user-set: skip nudging until global_prompt_count > this
    "disabled_rules": [],         # user can permanently silence a rule id
    # Encouragement layer (v0.3+). Sparing praise for the specific positive
    # behaviors mirroring the negative rules — evidence-based defaults tuned
    # for variable-ratio reinforcement without diluting nudges.
    # v0.9.0 — no permanent mastery. Mastered rules still evaluate; when
    # they match they emit a rare "refresher" instead of the full nudge.
    # Set mastered_cooldown_prompts to 0 to disable refresher firing entirely
    # (reverts to pre-0.9 behavior of permanent silence on mastered rules).
    "mastered_cooldown_prompts": 50,   # 10× the practicing cooldown
    # Auto-demotion (opt-in): if a mastered rule fires threshold+ times within
    # window prompts, demote back to practicing. Off by default — being
    # surprised by a graduated rule reactivating is unpleasant. Users who
    # want strict self-healing turn this on.
    "demote_on_regression": {"enabled": False, "threshold": 3, "window": 30},
    "praise_ratio": 10,           # 1 praise per N clean prompts with a positive
                                  # (variable-ratio). Kohn's don't-dilute-praise
                                  # threshold — sparing praise stays potent. If
                                  # you feel the layer "isn't working," check
                                  # log.md before dialing this down; it fires more
                                  # than you think, just invisibly (via
                                  # additionalContext to Claude).
    "praise_on_mastery": True,    # celebrate when a rule graduates to mastered
    "praise_on_first_after_fire": True,  # celebrate the immediate correction
    "disable_praise": False,      # silence all praise but keep nudges
    "praise_novelty_window": 5,   # don't repeat the same phrasing within N praises
    # Typo tolerance (v0.5+). Prompt is normalized against a curated set of
    # trigger words BEFORE rules run — makes the coach friendly to dyslexic
    # spellings, transpositions, and dropped letters. Levenshtein distance
    # based; only substitutes when there's a UNIQUE closest match within the
    # tolerance (ties = no correction, so "text" doesn't become "test").
    # Set to 0 to disable the normalization pass entirely.
    "typo_tolerance": 2,
    # LLM fallback (v0.6+, opt-in stub for now). If enabled AND no rule fired
    # via regex AND the prompt is long, an optional Haiku call would classify
    # against the rule catalog. Deferred until fuzzy normalization is proven
    # insufficient in real use.
    "llm_fallback": {"enabled": False, "model": None, "min_words": 20},
}


# ---------------------------------------------------------------------------
# Typo tolerance — Levenshtein-based prompt normalization
# ---------------------------------------------------------------------------

# English inflection suffixes that indicate a token is a legitimate English
# word (plural, past tense, gerund, adverb). Tokens ending in these are
# skipped by the normalizer — before v0.7.0 the coach was over-correcting
# `changes → change`, `tickets → ticket`, `implemented → implement`.
_ENGLISH_INFLECTION_SUFFIXES = ("s", "es", "ed", "ing", "ly", "er", "est",
                                "tion", "ment", "ness", "able", "ible")

# Common English words within edit distance 2 of a trigger word that would
# otherwise get falsely normalized. Evidence-based list (grow as false
# positives appear in log.md):
#   - `publish` was normalized to `polish` (loop refinement trigger)
_PROTECTED_ENGLISH_WORDS = frozenset({
    "publish", "please", "answer", "review", "reason",
    "finish", "punish", "release", "class", "field", "method",
    "issue", "ticket", "packet", "action", "always",
})


# Hand-curated set of trigger words drawn from the rule/positive regexes.
# Kept small on purpose — larger vocabularies increase false-positive risk on
# unrelated words. Add here when a rule's trigger word isn't being caught on
# common misspellings.
TRIGGER_WORDS: set[str] = {
    # actions
    "refactor", "rewrite", "migrate", "migration", "implement", "build",
    "update", "change", "remove", "delete", "rename", "extract",
    "deploy", "schema",
    # scope + adjectives
    "everything", "entire", "faster", "better", "improved", "cleaner",
    "smoother", "prettier", "nicer",
    # verification / DoD
    "verify", "verification", "expect", "assert", "coverage", "passes",
    # guardrails
    "guardrail", "preserve", "invariant", "stable", "unchanged", "intact",
    # reference / context
    "failing", "broken", "ticket", "regression",
    # format
    "bullet", "table", "markdown", "paragraph", "summary", "report",
    # reasoning / judgment
    "reason", "reasoning", "debug", "diagnose", "trace",
    "rubric", "criteria", "dimensions", "correctness",
    # uncertainty / investigation
    "uncertain", "unsure", "investigate", "identify", "locate",
    # loops / goals
    "iterate", "iteration", "refine", "polish",
    # tool-native
    "checklist", "propose", "workflow", "parallel", "explore",
    "reviewer", "skeptic", "security", "adversarial", "brainstorm", "panel",
    # skill-awareness
    "abstract", "template", "ceremony", "example",
    # very-common structural words used in rule triggers
    "again", "another", "review", "critique",
}


def _levenshtein(a: str, b: str, limit: int) -> int:
    """Banded Levenshtein distance with early exit at `limit + 1`."""
    la, lb = len(a), len(b)
    if abs(la - lb) > limit:
        return limit + 1
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        min_row = cur[0]
        ac = a[i - 1]
        for j in range(1, lb + 1):
            cost = 0 if ac == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if cur[j] < min_row:
                min_row = cur[j]
        if min_row > limit:
            return limit + 1
        prev = cur
    return prev[lb]


_CONVERSATIONAL_APPROVAL = re.compile(
    r"^(y|yes|yep|yeah|no|nope|nah|ok|okay|k|sure|go|"
    r"ship|publish|merge|push|deploy|"
    r"proceed|confirm|approved?|approve|"
    r"do it|go for it|ship it|send it|"
    r"continue|next|more|again|"
    r"thanks|thx|thank you|great|nice|perfect|cool|fine|good|done|got it|"
    r"👍|👎|✓|✔)$"
)
_CONVERSATIONAL_NUMERIC = re.compile(r"^#?\d+([\s,]+(and\s+)?#?\d+)*$")
_CONVERSATIONAL_LETTER = re.compile(r"^(option\s+)?[a-e]([\s,]+(and\s+)?[a-e])*$")
_CONVERSATIONAL_AFFIRM = re.compile(
    r"\b(yes|no|and|both|neither|either|but not|except|only|first|second|third)\b"
)
_CONVERSATIONAL_PICK = re.compile(r"\b\d+\b|\boption\s+[a-e]\b")

# v0.13.0 — bug-report marker phrases. When present in a prompt, the
# analyzer flags the PREVIOUS non-conversational prompt's analysis into
# `.claude/prompt-coach/candidates.jsonl` for later review via the
# /prompt-coach-beta:report-issue slash command.
_BUG_REPORT_PHRASE = re.compile(
    r"\b(coach\s+(that\s+was\s+|was\s+)?wrong|"
    r"coach\s+missed|"
    r"coach\s+mistreat(ed)?|"
    r"coach\s+false\s+positive|"
    r"coach\s+fp\b|"
    r"coach\s+shouldn.?t\s+have|"
    r"coach\s+bug|"
    r"bad\s+nudge|wrong\s+nudge|"
    r"report\s+(the\s+)?coach|"
    r"coach\s+oversight|"
    r"coach\s+wrong)\b",
    re.IGNORECASE,
)


def is_bug_report_phrase(prompt: str) -> bool:
    return bool(_BUG_REPORT_PHRASE.search(prompt))


def compute_signature(prompt: str, corrections: list[tuple[str, str]]
                      ) -> dict:
    """Compute a structural signature — enough to categorize the prompt
    class without leaking full content. Used in bug reports (first 5
    words only, plus these booleans)."""
    words = prompt.split()
    pl = prompt.lower()
    return {
        "word_count": len(words),
        "char_count": len(prompt),
        "first_5_words": " ".join(words[:5]),
        "starts_with_action": _starts_with_action(prompt),
        "starts_with_hedge": bool(_HEDGE_PREFIXES.match(pl.strip())),
        "has_file_ref": bool(re.search(
            r"\b\w+\.(py|js|ts|tsx|jsx|java|kt|go|rs|md|json|yaml|yml|"
            r"sh|toml|adoc|rst|html|css|sql)\b|src/|tests?/|lib/", prompt)),
        "has_ticket_id": bool(re.search(r"\b[A-Z]{2,}-\d+|#\d+", prompt)),
        "has_backticks": "`" in prompt,
        "has_url": bool(re.search(r"https?://", prompt)),
        "has_goal_clause": bool(re.search(
            r"\b(so that|because|in order to|we (are|have) (fully )?"
            r"(moved|migrated))\b", pl)),
        "has_guardrail_clause": bool(re.search(
            r"\b(don'?t\s+|do\s+not\s+|must\s+not|keep\s+.*\s+"
            r"(stable|intact|unchanged)|without\s+(breaking|changing))",
            pl)),
        "has_dod_marker": bool(re.search(
            r"\b(until|verify|passes|assert|expect|green|ci)\b", pl)),
        "has_format_spec": bool(re.search(
            r"\b(bullet|table|json|markdown|paragraph|numbered|"
            r"one[- ]liner|one line|yes/no|\d+\s*(items?|points?|bullets?))\b",
            pl)),
        "is_question": bool(re.match(
            r"^\s*(what|how|why|does|is there|are there|do we|do you|"
            r"can we|should we)\b", pl)),
        "is_conversational": is_conversational(prompt),
        "corrections_applied": [f"{o}->{c}" for o, c in corrections],
    }


def is_conversational(prompt: str) -> bool:
    """Detect short-turn responses — approvals, multi-choice picks, continuations —
    where the 'prompt' is really a fragment answering an implicit question and the
    coaching rules would misfire (Alex's dyslexic 'sure' or '1 and 2 yes 3').
    Skipped prompts still get logged for audit; they do not affect streaks."""
    p = prompt.strip()
    if not p:
        return True
    # Agent-orchestration messages — task notifications and system reminders
    # are not user prompts. They enter the hook because task-triggered wakes
    # pass through UserPromptSubmit, but they shouldn't count for coaching.
    if p.startswith("<task-notification>") or p.startswith("<system-reminder>"):
        return True
    pl = p.lower().rstrip(".!?,;: ")
    if _CONVERSATIONAL_APPROVAL.match(pl):
        return True
    if _CONVERSATIONAL_NUMERIC.match(pl):
        return True
    if _CONVERSATIONAL_LETTER.match(pl):
        return True
    # Mixed short pick + affirmation, e.g. "1 and 2 yes 3 no 4"
    if len(pl.split()) <= 12:
        if _CONVERSATIONAL_PICK.search(pl) and _CONVERSATIONAL_AFFIRM.search(pl):
            return True
    return False


def _match_case(pattern: str, target: str) -> str:
    """Approximate the original token's capitalization on the corrected word."""
    if not pattern:
        return target
    if pattern.isupper():
        return target.upper()
    if pattern[0].isupper():
        return target.capitalize()
    return target


def normalize_prompt(prompt: str, tolerance: int
                     ) -> tuple[str, list[tuple[str, str]]]:
    """Fuzzy-match tokens in the prompt against TRIGGER_WORDS; substitute the
    UNIQUE closest match within `tolerance` edits. Skip tokens that are
    < 5 chars, already trigger words, or have a tie for closest.
    Returns (normalized_prompt, [(original, corrected), ...]).
    """
    if tolerance <= 0:
        return prompt, []

    corrections: list[tuple[str, str]] = []
    parts = re.split(r"(\W+)", prompt)  # keep separators between tokens
    out_parts: list[str] = []
    for tok in parts:
        if not tok or not tok.isascii() or not re.match(r"^[A-Za-z]+$", tok):
            out_parts.append(tok)
            continue
        if len(tok) < 5:
            out_parts.append(tok)
            continue
        low = tok.lower()
        if low in TRIGGER_WORDS:
            out_parts.append(tok)
            continue
        # v0.7.0 — protect a curated set of common English words that are
        # within edit distance 2 of a trigger (publish ↔ polish, etc.).
        if low in _PROTECTED_ENGLISH_WORDS:
            out_parts.append(tok)
            continue

        # Adaptive tolerance: shorter tokens get stricter matching because
        # false-positive rate at distance 2 is much higher for 5-6 char words
        # (e.g. "public" ↔ "rubric" both length 6). Longer tokens tolerate
        # transpositions (dist 2) since real typos there are more common than
        # coincidental collisions.
        adaptive = min(1, tolerance) if len(low) <= 6 else tolerance
        best_word: str | None = None
        best_dist = adaptive + 1
        ties = 0
        for kw in TRIGGER_WORDS:
            if abs(len(kw) - len(low)) > adaptive:
                continue
            d = _levenshtein(low, kw, best_dist)
            if d < best_dist:
                best_word, best_dist, ties = kw, d, 1
            elif d == best_dist:
                ties += 1

        if best_word and best_dist <= adaptive and ties == 1:
            # v0.7.0 — protect legitimate English inflections. Only skip if
            # the "correction" is JUST stripping a productive English suffix
            # (target == token minus suffix). Real typos have insertions or
            # substitutions elsewhere, not just a suffix strip.
            # Evidence from v0.6.0 log: changes→change, tickets→ticket,
            # implemented→implement were all suffix strips of valid English.
            is_suffix_strip = any(
                low.endswith(sfx) and low[: -len(sfx)] == best_word
                for sfx in _ENGLISH_INFLECTION_SUFFIXES
            )
            if is_suffix_strip:
                out_parts.append(tok)
                continue
            corrected = _match_case(tok, best_word)
            corrections.append((tok, corrected))
            out_parts.append(corrected)
        else:
            out_parts.append(tok)

    return "".join(out_parts), corrections

# ---------------------------------------------------------------------------
# Rule catalog
# ---------------------------------------------------------------------------

@dataclass
class Rule:
    id: str
    tier: int                     # 1 = fundamentals, 2 = intermediate, 3 = advanced
    name: str
    nudge: str
    guidance: str                 # short hint for Claude's additionalContext
    sources: list[tuple[str, str]]  # (title, url)
    check: Callable[[str], bool]


# ---- L1 fundamentals -------------------------------------------------------

def _first_line(p: str) -> str:
    for line in p.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _has_referent(text: str) -> bool:
    """A concrete pointer near the pronoun disqualifies vague-reference."""
    return bool(re.search(
        r"`[^`]+`|\S+\.(py|js|ts|tsx|jsx|java|kt|go|rs|md|json|yaml|yml|sh)\b"
        r"|(?<!\w)/[\w\-./]+|#\d+|@[\w\-]+|\bhttps?://",
        text,
    ))


def rule_vague_reference(prompt: str) -> bool:
    first = _first_line(prompt).lower()
    if len(first.split()) < 3:
        return False
    pronoun = re.search(r"\b(it|this|that|these|those|the thing)\b", first)
    if not pronoun:
        return False
    return not _has_referent(first)


ACTION_VERBS = (
    "add", "build", "fix", "refactor", "implement", "create", "change",
    "update", "make", "write", "rewrite", "remove", "delete", "rename",
    "extract", "migrate", "wire", "hook",
    # v0.7.0 — real-session-observed action verbs that were being missed
    "move", "open", "close", "branch", "merge", "file", "format",
    "install", "configure", "enable", "disable", "bump", "pin",
    "strip", "gitignore",
    # v0.11.0 — release-family verbs (evidence: "try to deploy" fired
    # nothing in real log). Deploys are near-always guardrail-worthy.
    "deploy", "publish", "release", "ship",
    # v0.12.0 — real-session dev-workflow verb, evidence:
    # "commit and check infra for creds" fired nothing.
    "commit",
)

# Hedge prefixes — real English people prepend to action asks. Strip them
# so "try to deploy" is analyzed as "deploy". v0.11.0.
_HEDGE_PREFIXES = re.compile(
    r"^(try to|try and|let'?s|going to|gonna|need to|"
    r"want to|wanna|should|could|would|might|"
    r"please|can you|could you|would you)\s+"
)

# Multi-word action phrases that count as an action start (v0.7.0).
_MULTIWORD_ACTIONS = re.compile(
    r"^(get\s+rid\s+of|clean\s+up|set\s+up|tear\s+down|shut\s+down|"
    r"back\s+up|hook\s+up|wire\s+up)\b"
)


def _starts_with_action(prompt: str) -> bool:
    first = _first_line(prompt).lower().lstrip("- *#>")
    # v0.11.0 — strip hedge prefixes ("try to X", "let's X", "need to X",
    # "should X"), then re-check for an action verb. Real prompts are
    # rarely bare imperatives; most start with a hedge word.
    m = _HEDGE_PREFIXES.match(first)
    if m:
        first = first[m.end():]
    if any(first.startswith(v + " ") or first == v for v in ACTION_VERBS):
        return True
    return bool(_MULTIWORD_ACTIONS.match(first))


def rule_no_definition_of_done(prompt: str) -> bool:
    if not _starts_with_action(prompt):
        return False
    pl = prompt.lower()
    dod_markers = (
        "until ", "verify", "test", "check ", "ensure", " so that ", "passes",
        "green", " ci ", "expect", "assert", "output should", "should return",
        "should match", "coverage", "no error", "no warning", "definition of done",
        "acceptance",
    )
    return not any(m in pl for m in dod_markers)


def rule_unbounded_scope(prompt: str) -> bool:
    pl = prompt.lower()
    unbounded = re.search(r"\b(all|everything|every|entire|the whole)\b", pl)
    if not unbounded:
        return False
    action = re.search(
        r"\b(refactor|rewrite|clean|fix|update|rename|remove|delete|touch|migrate)\b",
        pl,
    )
    if not action:
        return False
    scoped = re.search(
        r"\b(only|except|under\s+\S+|in\s+\S+|matching|starting with|"
        r"whose|where|within|limited to|scoped to)\b",
        pl,
    )
    return not bool(scoped)


def rule_improve_without_metric(prompt: str) -> bool:
    pl = prompt.lower()
    fuzzy = re.search(
        r"\b(better|improved?|cleaner|nicer|smoother|faster|prettier|"
        r"more\s+\w+|less\s+\w+)\b",
        pl,
    )
    if not fuzzy:
        return False
    metric = re.search(
        r"\b\d+\s*(%|ms|s|second|seconds|kb|mb|ms\b|x\b)"
        r"|\bby\s+\d|\bunder\s+\d|\bfrom\s+\d.*\bto\s+\d"
        r"|test\w*\s+pass|failing\s+test|assert|matches?|so that|"
        r"benchmark|profile\s+shows|regress",
        pl,
    )
    return not bool(metric)


def rule_missing_guardrails(prompt: str) -> bool:
    pl = prompt.lower()
    heavy_action = re.search(
        # v0.11.0 — added deploy/publish/release/ship (deploys are almost
        # always guardrail-worthy in practice) + reset/wipe/purge.
        r"\b(refactor|rewrite|migrate|move|rename|delete|remove|replace|"
        r"deploy|publish|release|ship|reset|wipe|purge)\b",
        pl,
    )
    if not heavy_action:
        return False
    guardrail = re.search(
        r"(don'?t\s+|do\s+not\s+|must\s+not|without\s+(breaking|changing|touching)|"
        r"keep\s+.*\s+(stable|intact|unchanged|as\s+is|working)|"
        r"preserve|leave\s+.*\s+alone|no\s+changes?\s+to|"
        r"backwards[- ]compatible|api[- ]compatible|no\s+breaking)",
        pl,
    )
    return not bool(guardrail)


# ---- L2 intermediate -------------------------------------------------------

def rule_compound_tasks(prompt: str) -> bool:
    pl = prompt.lower()
    verbs = "|".join(ACTION_VERBS)
    joins = len(re.findall(
        rf"\s+(?:and|then|also|plus|,)\s+(?:{verbs})\b", pl))
    return joins >= 2


def rule_no_verify_loop(prompt: str) -> bool:
    if not _starts_with_action(prompt):
        return False
    pl = prompt.lower()
    verify = re.search(
        r"\b(run\s+tests?|test\s+it|verify|check\s+that|make\s+sure|"
        r"confirm|assert|expect|passes\s+ci|green\s+build)\b", pl)
    return not bool(verify)


def rule_missing_context_fetch(prompt: str) -> bool:
    pl = prompt.lower()
    role_refs = re.search(
        r"\b(the\s+failing\s+test|the\s+broken\s+test|the\s+recent\s+pr|"
        r"the\s+last\s+commit|the\s+issue|the\s+ticket|that\s+error|"
        r"the\s+bug|the\s+regression)\b", pl)
    if not role_refs:
        return False
    ids = re.search(
        r"#\d+|\bpr\s+\d+|test\w*\s+\w+::\w+|`[^`]+`|https?://",
        prompt,
    )
    return not bool(ids)


def rule_no_answer_shape(prompt: str) -> bool:
    """Information-seeking question with no format spec — evidence: real
    prompts like 'what are lsp servers', 'how much of github app support
    do we have?', 'Do we have enough for release?', and 'Are there java
    libs...' were firing nothing at all.

    v0.12.0: elevated from L2 → L1 (fundamentals) and broadened q regex
    to include 'do we / does it / can we / should we / are there'
    forms."""
    pl = prompt.lower()
    q = re.search(
        r"^\s*(what (are|is|kinds|types|options)|"
        r"how (much|many|do|does|can|should|would)|"
        r"which \w+ (should|are|is|would)|why (should|is|are|does|doesn.?t)|"
        r"does (\w+ )?exist|is there|are there|"
        # v0.12.0 additions — real English question forms
        r"do (we|you|they|i)|does (it|he|she|this|that)|"
        r"did (we|you|they|i|it|this)|"
        r"can (we|you|i|it|this)|should (we|you|i|it|this)|"
        r"can i|should i)\b", pl)
    if not q:
        return False
    shape = re.search(
        r"\b(bullet|table|json|markdown|paragraph|numbered|"
        r"\d+\s*(items?|points?|rows?|bullets?|paragraphs?|words?|lines?)|"
        r"one[- ]liner|one line|short|long|detailed|brief|sentence|"
        r"yes/no|y/n|"
        r"columns?|rows?|schema|section|per\s+\w+|"
        r"under\s+\d+\s+words?|less than \d)\b", pl)
    return not bool(shape)


def rule_no_format_spec(prompt: str) -> bool:
    pl = prompt.lower()
    ask = re.search(
        r"\b(give\s+me|show\s+me|list|summari[sz]e|generate|produce|write)\b"
        r".{0,40}\b(summary|report|answer|list|table|analysis|breakdown|overview|plan)\b",
        pl,
    )
    if not ask:
        return False
    shape = re.search(
        r"\b(bullet|table|json|markdown|paragraph|numbered|"
        r"\d+\s*(items?|points?|rows?|bullets?|paragraphs?)|"
        r"columns?|rows?|schema|section|per\s+\w+)\b",
        pl,
    )
    return not bool(shape)


# ---- L3 advanced -----------------------------------------------------------

def rule_no_adversarial_check(prompt: str) -> bool:
    pl = prompt.lower()
    stakes = re.search(
        r"\b(security|auth|password|token|secret|migration|production|"
        r"deploy|drop\s+table|delete|remove\s+\w+\s+column|schema\s+change)\b",
        pl,
    )
    if not stakes:
        return False
    adversarial = re.search(
        r"\b(review|critique|adversarial|skeptic|refute|challenge|"
        r"edge\s+case|risk|threat|panel|red[- ]team|second\s+opinion)\b",
        pl,
    )
    return not bool(adversarial)


def rule_retry_without_diagnosis(prompt: str) -> bool:
    pl = prompt.lower().strip()
    if len(pl) > 140:
        return False
    retry = re.search(
        r"^(try\s+again|do\s+it\s+again|again[.?!]?$|redo|"
        r"still\s+(not|doesn.?t|broken|fails)|nope|not\s+working)",
        pl,
    )
    if not retry:
        return False
    diagnosis = re.search(
        r"\b(because|the\s+error|it\s+says|log|trace|stderr|"
        r"stack\s+trace|output\s+was|now\s+it\s+fails)\b", pl)
    return not bool(diagnosis)


def rule_no_few_shot(prompt: str) -> bool:
    pl = prompt.lower()
    pattern = re.search(
        r"\b(like|similar to|in the style of|matching|same pattern|"
        r"same as|following the same|analogous to|the way \w+ does)\b", pl)
    if not pattern:
        return False
    example = re.search(
        r"```|for example|e\.g\.|for instance|"
        r"\b(?:example|sample|input|output|given)\s*[:\-]",
        prompt, re.IGNORECASE)
    return not bool(example)


def rule_no_chain_of_thought(prompt: str) -> bool:
    pl = prompt.lower()
    hard = re.search(
        r"\b(why does|why doesn.?t|debug|diagnose|figure out|"
        r"trace|root cause|explain the difference|reason about|"
        r"analyz[e|ing] (this|the|these|those))\b", pl)
    if not hard:
        return False
    think = re.search(
        r"\b(think|reason|work through|step by step|"
        r"before (you )?answer|show your (work|reasoning)|"
        r"first .* then|analyze (this|it|then)|plan .* first)\b", pl)
    return not bool(think)


def rule_no_rubric(prompt: str) -> bool:
    pl = prompt.lower()
    judge = re.search(
        r"\b(is this(?:\s+\w+){0,3}\s+(good|correct|ok|fine|right|acceptable)|"
        r"is it(?:\s+\w+){0,3}\s+(good|correct|ok|fine)|"
        r"rate this|rank these|which is better|which one is (best|better)|"
        r"assess|evaluate|grade this)\b", pl)
    if not judge:
        return False
    rubric = re.search(
        r"\b(rubric|criteria|dimensions?|axis|axes|"
        r"scored on|graded on|based on:|against .* (spec|criteria)|"
        r"on\s+(correctness|performance|readability|simplicity|"
        r"safety|rollback|clarity))\b", pl)
    return not bool(rubric)


def rule_no_uncertainty_budget(prompt: str) -> bool:
    pl = prompt.lower()
    investigative = re.search(
        r"\b(find (out|whether)|figure out|investigate|search for|"
        r"locate|identify|determine|is there|are there|does .* exist)\b", pl)
    if not investigative:
        return False
    uncertainty = re.search(
        r"(if (you'?re |you are )?(unsure|not sure|uncertain|unclear)|"
        r"when in doubt|if you can'?t|otherwise say so|"
        r"flag if|admit if|prefer .* over guessing)", pl)
    return not bool(uncertainty)


# ---- L4 goals & loops ------------------------------------------------------

def rule_implicit_goal(prompt: str) -> bool:
    if not _starts_with_action(prompt):
        return False
    pl = prompt.lower()
    goal_markers = re.search(
        r"(\bso that\b|\bbecause\b|\bgoal is\b|\bgoal:|"
        r"\bin order to\b|\bto (make|enable|allow|support|prevent|"
        r"fix|reduce|increase|avoid|unblock|match)\b|"
        r"\bwe want to\b|\bthe point is\b|\bwhy: )", pl)
    return not bool(goal_markers)


def rule_unbounded_iteration(prompt: str) -> bool:
    pl = prompt.lower()
    loop = re.search(
        r"\b(keep (going|improving|refining|iterating|trying)|"
        r"iterate on|polish more|make it (even )?(better|cleaner|"
        r"nicer|tighter)|keep at it)\b", pl)
    if not loop:
        return False
    stop = re.search(
        r"\b(until|when|once|stop when|target:|goal:|score of|"
        r"passes|matches|below \d|under \d|no more \w+|"
        r"at most \d|max \d)\b", pl)
    return not bool(stop)


def rule_no_rubric_for_refine(prompt: str) -> bool:
    pl = prompt.lower()
    refine = re.search(
        r"\b(refine|iterate on|make (it|this) (better|cleaner|"
        r"nicer|tighter)|polish|rework|revise|another pass|"
        r"another round)\b", pl)
    if not refine:
        return False
    # A rubric names axes/criteria. Stopping conditions ('until', 'so that')
    # are covered by other rules — don't double-count them here.
    rubric = re.search(
        r"\b(rubric|criteria|scored on|dimensions?|axes|axis|"
        r"target:|axes:|"
        r"(more|less)\s+(correct|readable|performant|maintainable|"
        r"concise|robust|tested)|"
        r"on\s+(correctness|performance|readability|clarity|size|brevity)|"
        r"api stays|preserve|invariant)\b", pl)
    return not bool(rubric)


# ---- L5 Claude-Code tool-native --------------------------------------------

def rule_no_plan_mode_for_risky(prompt: str) -> bool:
    pl = prompt.lower()
    risky = re.search(
        r"\b(migrate|migration|schema change|drop (table|column)|"
        r"delete\s+(all|the)|rewrite the (module|package|whole)|"
        r"refactor the (whole|entire|core)|breaking change|"
        r"deploy to prod|production data|change the api)\b", pl)
    if not risky:
        return False
    plan_asked = re.search(
        r"\b(plan|propose|design|outline|approach|strategy|"
        r"dry.?run|preview|walk (me )?through|plan mode|"
        r"before (doing|touching|editing))\b", pl)
    return not bool(plan_asked)


def rule_no_task_list_for_multi_step(prompt: str) -> bool:
    pl = prompt.lower()
    verbs = "|".join(ACTION_VERBS)
    step_count = len(re.findall(rf"\b(?:{verbs})\b", pl))
    if step_count < 3:
        return False
    task_asked = re.search(
        r"\b(task list|todo|todos|track progress|break it down|"
        r"checklist|steps?:|numbered list|use taskcreate|plan\b)\b", pl)
    return not bool(task_asked)


def rule_no_agents_for_parallel_lookup(prompt: str) -> bool:
    pl = prompt.lower()
    multi_lookup = re.search(
        r"\b(and also (find|check|look|search|verify)|"
        r"search for .* and .* and|"
        r"(find|check|verify) .* in \S+ and (find|check|verify) .* in \S+|"
        r"look up .* and .*|both .* and .*)\b", pl)
    if not multi_lookup:
        return False
    parallel = re.search(
        r"\b(in parallel|concurrent|fan[- ]out|agents?|subagents?|"
        r"explore|multiple lookups|separate agents)\b", pl)
    return not bool(parallel)


def rule_no_role_for_critique(prompt: str) -> bool:
    pl = prompt.lower()
    critique = re.search(
        r"\b(review (this|my|the|results|findings|changes|code|output|design|plan)|"
        r"code review|critique|"
        r"find issues|find bugs|is this correct|check my|"
        r"look over|red[- ]team|nitpick|"
        r"assess (this|the|these|my)|evaluate (this|the|these|my))\b", pl)
    if not critique:
        return False
    role = re.search(
        r"/roles:as|/roles:|/brainstorm|/panel|/review-agents|"
        r"\breviewer\b|\bskeptic\b|security[- ]review|adversarial|"
        r"as a \w+ engineer|from .* perspective|multiple agents", pl)
    return not bool(role)


def rule_no_panel_for_contested_design(prompt: str) -> bool:
    pl = prompt.lower()
    fork = re.search(
        r"\b(should i (use|do|pick|go with)|which is better|"
        r"which one (should|would)|debate|trade[- ]?off|"
        r"option a.*option b|approach a.*approach b|"
        r"split opinion|torn between|weighing)\b", pl)
    if not fork:
        return False
    panel = re.search(
        r"\b(panel|brainstorm|multiple perspectives?|opposing views?|"
        r"steelman|/brainstorm|/panel|adversarial review)\b", pl)
    return not bool(panel)


def rule_no_skill_lookup(prompt: str) -> bool:
    pl = prompt.lower()
    ask = re.search(
        r"\b(how do i|how would i|what.?s the pattern for|"
        r"we need a way to|is there a good way to|"
        r"what.?s the standard way|what.?s the best way to)\b", pl)
    if not ask:
        return False
    already_checked = re.search(
        r"\b(skill|/help|existing|already have|is there a skill|"
        r"/roles?|/tune|/screenshot|/brainstorm|/dev-crew|"
        r"/research-sweep|/security-audit|/implement-issue|"
        r"/maven-quality|plugin catalog)\b", pl)
    return not bool(already_checked)


def rule_pattern_worth_abstracting(prompt: str) -> bool:
    pl = prompt.lower()
    repeat = re.search(
        r"\bagain\b|\bonce more\b|\bsame as (last time|before)\b|"
        r"\byet another\b|\bthird time\b|\bnth time\b|"
        r"\bkeep having to\b|\bevery time i\b|"
        r"\bfor the third time\b|\b3rd time\b", pl)
    if not repeat:
        return False
    considered = re.search(
        r"\b(skill|abstract|extract|template|reusable|"
        r"automate|make a skill|/roles|plugin)\b", pl)
    return not bool(considered)


def rule_no_skill_composition(prompt: str) -> bool:
    pl = prompt.lower()
    steps = re.search(
        r"\b(first .* then|step 1 .* step 2|then .* then .* then|"
        r"the process is|the workflow is)\b", pl)
    if not steps:
        return False
    repeat_signal = re.search(
        r"\b(every time|whenever|process|workflow|routine|"
        r"checklist|for future|going forward|from now on)\b", pl)
    if not repeat_signal:
        return False
    considered = re.search(
        r"\b(skill|make this a|extract|automate|"
        r"turn this into|codify|reusable)\b", pl)
    return not bool(considered)


def rule_no_workflow_for_fanout(prompt: str) -> bool:
    pl = prompt.lower()
    fanout = re.search(
        r"\b(for each|across (all|every|these)|iterate over|"
        r"one by one|do this (to|for) (all|every|each))\b", pl)
    if not fanout:
        return False
    counted = re.search(
        r"\b([5-9]|1\d|2\d|3\d|4\d|5\d|\d{3,})\s+"
        r"(files|items|repos|entries|records|rows|things|"
        r"tests|packages|modules|targets|methods|classes|projects)\b",
        pl)
    if not counted:
        return False
    workflow = re.search(
        r"\b(workflow|fan[- ]out|parallel|agents?|"
        r"/workflow|ultracode|pipeline)\b", pl)
    return not bool(workflow)


# ---- Catalog ---------------------------------------------------------------

SRC_ANTHROPIC_BE_CLEAR = ("Anthropic — Be clear and direct",
                          "https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/be-clear-and-direct")
SRC_ANTHROPIC_OVERVIEW = ("Anthropic — Prompt engineering overview",
                          "https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview")
SRC_ANTHROPIC_CHAIN = ("Anthropic — Chain complex prompts",
                       "https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/chain-prompts")
SRC_CC_BESTPRACTICE = ("Claude Code — Best practices",
                       "https://www.anthropic.com/engineering/claude-code-best-practices")
SRC_OPENAI_GUIDE = ("OpenAI — Prompt engineering guide",
                    "https://platform.openai.com/docs/guides/prompt-engineering")
SRC_SIMONW = ("Simon Willison — Prompt engineering notes",
              "https://simonwillison.net/tags/promptengineering/")
SRC_PROMPT_REPORT = ("Schulhoff et al. — The Prompt Report (2024)",
                     "https://arxiv.org/abs/2406.06608")
SRC_ANTHROPIC_MULTISHOT = ("Anthropic — Multishot prompting (give examples)",
                           "https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/multishot-prompting")
SRC_ANTHROPIC_COT = ("Anthropic — Let Claude think (chain of thought)",
                     "https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/chain-of-thought")
SRC_WEI_COT = ("Wei et al. — Chain-of-Thought prompting elicits reasoning (2022)",
               "https://arxiv.org/abs/2201.11903")
SRC_BROWN_FEWSHOT = ("Brown et al. — Language models are few-shot learners (2020)",
                     "https://arxiv.org/abs/2005.14165")
SRC_CC_HOOKS = ("Claude Code — Hooks, subagents, and the Task tool",
                "https://docs.anthropic.com/en/docs/claude-code/hooks")

# Encouragement layer sources (v0.3+)
SRC_MUELLER_DWECK = ("Mueller & Dweck — Praise for intelligence can undermine motivation (1998)",
                     "https://psycnet.apa.org/doi/10.1037/0022-3514.75.1.33")
SRC_DWECK_MINDSET = ("Dweck — Mindset: The New Psychology of Success (2006)",
                     "https://mindsetworks.com/")
SRC_FOGG_TINY = ("Fogg — Tiny Habits: The Small Changes That Change Everything (2019)",
                 "https://tinyhabits.com/")
SRC_BROPHY_PRAISE = ("Brophy — Teacher Praise: A Functional Analysis (1981)",
                     "https://journals.sagepub.com/doi/10.3102/00346543051001005")
SRC_DECI_RYAN = ("Deci & Ryan — Self-determination theory and intrinsic motivation (2000)",
                 "https://selfdeterminationtheory.org/")
SRC_KOHN_REWARDS = ("Kohn — Punished by Rewards (1993)",
                    "https://www.alfiekohn.org/punished-rewards/")

# Skill-awareness sources (v0.4+)
SRC_FOWLER_REFACTOR = ("Fowler — Refactoring: the rule of three (2nd ed., 2018)",
                       "https://martinfowler.com/books/refactoring.html")
SRC_KENT_BECK_YAGNI = ("Kent Beck — YAGNI (You Aren't Gonna Need It, XP)",
                       "http://www.extremeprogramming.org/rules/early.html")
SRC_ANTHROPIC_SKILLS = ("Anthropic — Claude Code Skills",
                        "https://docs.anthropic.com/en/docs/claude-code/skills")
SRC_MCILROY_UNIX = ("McIlroy — The Unix philosophy (composition, do one thing well)",
                    "https://en.wikipedia.org/wiki/Unix_philosophy")
SRC_NORMAN_DESIGN = ("Norman — The Design of Everyday Things: discoverability",
                     "https://mitpress.mit.edu/9780262525671/the-design-of-everyday-things/")


RULES: list[Rule] = [
    Rule(
        id="vague-reference",
        tier=1,
        name="Vague reference",
        nudge=(
            "Your first sentence points with 'it/this/that' but doesn't name what. "
            "Try naming the file, function, PR, or topic — one concrete pointer "
            "removes an entire class of ambiguity."
        ),
        guidance=(
            "User's prompt starts with an unresolved pronoun. If context makes the "
            "referent unambiguous, proceed; otherwise ask ONE short clarifying "
            "question before diving in."
        ),
        sources=[SRC_ANTHROPIC_BE_CLEAR, SRC_CC_BESTPRACTICE],
        check=rule_vague_reference,
    ),
    Rule(
        id="no-definition-of-done",
        tier=1,
        name="No definition of done",
        nudge=(
            "You asked for an action but didn't say what 'done' looks like. "
            "Add one line: which tests pass, which behavior appears, or what "
            "output shape you expect."
        ),
        guidance=(
            "User's prompt is an action verb with no acceptance criteria. Before "
            "acting, restate your interpretation of 'done' in one sentence, and "
            "invite a correction if it's wrong."
        ),
        sources=[SRC_ANTHROPIC_BE_CLEAR, SRC_CC_BESTPRACTICE, SRC_SIMONW],
        check=rule_no_definition_of_done,
    ),
    Rule(
        id="unbounded-scope",
        tier=1,
        name="Unbounded scope",
        nudge=(
            "'All/every/whole' with an action verb is a scope trap. Constrain: "
            "which files, which module, which pattern — or say 'audit only, no "
            "changes' if that's the real ask."
        ),
        guidance=(
            "User's prompt has an unbounded scope word attached to a mutating "
            "verb. Ask them to constrain (path glob, module, or read-only) BEFORE "
            "doing multi-file edits."
        ),
        sources=[SRC_ANTHROPIC_OVERVIEW, SRC_CC_BESTPRACTICE],
        check=rule_unbounded_scope,
    ),
    Rule(
        id="improve-without-metric",
        tier=1,
        name="Improve without a metric",
        nudge=(
            "'Better/faster/cleaner' means different things to different readers. "
            "Pin it: 'p95 under 200 ms', 'no cast warnings', 'passes this failing "
            "test', 'reads in under 20 lines'."
        ),
        guidance=(
            "User asked for improvement without a measurable target. Either infer "
            "the most likely target from context and STATE it before acting, or "
            "ask which axis matters most (correctness, speed, clarity, size)."
        ),
        sources=[SRC_ANTHROPIC_BE_CLEAR, SRC_OPENAI_GUIDE, SRC_PROMPT_REPORT],
        check=rule_improve_without_metric,
    ),
    Rule(
        id="missing-guardrails",
        tier=1,
        name="Missing guardrails",
        nudge=(
            "Heavy verbs (refactor / rewrite / migrate) without a 'do not touch' "
            "clause invite over-reach. Name one thing that MUST stay stable: API, "
            "behavior, filenames, tests."
        ),
        guidance=(
            "User's prompt has a broad mutating verb and no invariant. State the "
            "invariants you'll preserve (public API, existing tests, file "
            "structure) in your plan, and confirm before large changes."
        ),
        sources=[SRC_ANTHROPIC_CHAIN, SRC_CC_BESTPRACTICE],
        check=rule_missing_guardrails,
    ),
    # ---- L2 ----
    Rule(
        id="compound-tasks",
        tier=2,
        name="Compound tasks",
        nudge=(
            "Three or more action verbs joined by 'and' turn into partial work. "
            "Split into ordered steps, or say which is P0 and which can wait."
        ),
        guidance=(
            "User's prompt bundles multiple mutations. Propose an ordered plan "
            "with the smallest independently-verifiable slice first; ask which "
            "to skip if any."
        ),
        sources=[SRC_ANTHROPIC_CHAIN, SRC_PROMPT_REPORT],
        check=rule_compound_tasks,
    ),
    Rule(
        id="no-verify-loop",
        tier=2,
        name="No verify loop",
        nudge=(
            "You asked for an implementation but not for verification. Add "
            "'and run tests / confirm build passes / show me the failing case "
            "reproduces then fixed'."
        ),
        guidance=(
            "User's prompt implements without verifying. Run the relevant tests / "
            "type-check / build after your change, and report the result even if "
            "they didn't ask."
        ),
        sources=[SRC_CC_BESTPRACTICE, SRC_ANTHROPIC_CHAIN],
        check=rule_no_verify_loop,
    ),
    Rule(
        id="missing-context-fetch",
        tier=2,
        name="Missing context reference",
        nudge=(
            "You referred to 'the failing test' / 'the issue' / 'that error' — "
            "but didn't cite it. Paste the ID, name, or error text so Claude "
            "doesn't guess."
        ),
        guidance=(
            "User referenced an external artifact by role but not by ID. Ask "
            "for the identifier (issue #, test name, error string) before "
            "investigating, unless a single obvious candidate exists."
        ),
        sources=[SRC_ANTHROPIC_BE_CLEAR, SRC_CC_BESTPRACTICE],
        check=rule_missing_context_fetch,
    ),
    Rule(
        id="no-answer-shape",
        tier=1,
        name="Information ask without a shape",
        nudge=(
            "'What are X' / 'how much of Y' — you'll get a wall of prose. "
            "Add a shape: '3-bullet summary each', 'one-liner per', 'under "
            "100 words', or 'yes/no + one sentence why'."
        ),
        guidance=(
            "User asked an information-seeking question without specifying "
            "shape. Pick a compact default upfront (e.g. 'I'll give you 3 "
            "bullets each') and STATE it before answering; the user can "
            "redirect if the shape is wrong."
        ),
        sources=[SRC_OPENAI_GUIDE, SRC_ANTHROPIC_OVERVIEW, SRC_ANTHROPIC_BE_CLEAR],
        check=rule_no_answer_shape,
    ),
    Rule(
        id="no-format-spec",
        tier=2,
        name="No output shape",
        nudge=(
            "You asked for a summary / list / report without a shape. Give "
            "one: '5 bullets', 'table with columns X/Y/Z', 'under 200 words'."
        ),
        guidance=(
            "User asked for structured output without specifying structure. Pick "
            "a compact default (bullets ≤ 7, or a small table) and STATE it "
            "before writing; user can redirect."
        ),
        sources=[SRC_OPENAI_GUIDE, SRC_ANTHROPIC_OVERVIEW],
        check=rule_no_format_spec,
    ),
    # ---- L3 ----
    Rule(
        id="no-adversarial-check",
        tier=3,
        name="No adversarial check",
        nudge=(
            "High-stakes area (security / migration / prod / deletes). Ask "
            "for an adversarial pass: 'what would a skeptic attack here?', "
            "'list 3 ways this breaks under concurrency'."
        ),
        guidance=(
            "User's prompt is high-stakes. Before acting, list 2–3 concrete "
            "failure modes and either address or explicitly accept each. Offer "
            "an adversarial-review pass."
        ),
        sources=[SRC_ANTHROPIC_CHAIN, SRC_PROMPT_REPORT, SRC_SIMONW],
        check=rule_no_adversarial_check,
    ),
    Rule(
        id="retry-without-diagnosis",
        tier=3,
        name="Retry without diagnosis",
        nudge=(
            "'Try again' with no new info tends to loop. Add: what failed, "
            "what the error said, what you tried, what you expected."
        ),
        guidance=(
            "User is retrying without new context. BEFORE re-attempting, restate "
            "what you understood failed last round; if unclear, ask for the error "
            "text or the test output."
        ),
        sources=[SRC_ANTHROPIC_CHAIN, SRC_CC_BESTPRACTICE],
        check=rule_retry_without_diagnosis,
    ),
    Rule(
        id="no-few-shot",
        tier=3,
        name="Pattern ask without example",
        nudge=(
            "You asked for something 'like X' or 'in the same style' but didn't "
            "show one. Paste a 2–3 line example — few-shot demonstrations beat "
            "descriptions almost every time."
        ),
        guidance=(
            "User asked for pattern-matched output without providing an exemplar. "
            "Ask for one small example, or pick a plausible one from context and "
            "state your assumption explicitly before writing."
        ),
        sources=[SRC_ANTHROPIC_MULTISHOT, SRC_BROWN_FEWSHOT, SRC_PROMPT_REPORT],
        check=rule_no_few_shot,
    ),
    Rule(
        id="no-chain-of-thought",
        tier=3,
        name="Hard reasoning without 'think first'",
        nudge=(
            "You asked a why/debug/trace/root-cause question. Add 'think through "
            "this first' or 'reason step by step before answering' — CoT is a "
            "well-known accuracy lift on reasoning tasks."
        ),
        guidance=(
            "User asked a reasoning question. Think through the problem "
            "explicitly in your response (not silently) before stating the "
            "conclusion — restate the question, list what you know, then reason."
        ),
        sources=[SRC_ANTHROPIC_COT, SRC_WEI_COT, SRC_PROMPT_REPORT],
        check=rule_no_chain_of_thought,
    ),
    Rule(
        id="no-rubric",
        tier=3,
        name="Judgment without rubric",
        nudge=(
            "'Is this good?' means nothing without a rubric. Add the axes you "
            "care about: correctness, performance, readability, size — or point "
            "to the spec it's judged against."
        ),
        guidance=(
            "User asked for a judgment without criteria. Propose a rubric (3–5 "
            "axes with a scale) BEFORE evaluating; invite the user to correct "
            "the axes; then apply it and report per-axis, not overall."
        ),
        sources=[SRC_ANTHROPIC_BE_CLEAR, SRC_PROMPT_REPORT, SRC_OPENAI_GUIDE],
        check=rule_no_rubric,
    ),
    Rule(
        id="no-uncertainty-budget",
        tier=3,
        name="Investigative ask without uncertainty budget",
        nudge=(
            "'Find whether X' or 'does Y exist' without an 'if unsure, say so' "
            "clause tempts a confident guess. Add: 'if you can't verify, tell me "
            "what you'd need to.'"
        ),
        guidance=(
            "User asked an investigative question. When answering, distinguish "
            "verified findings from inference; if you can't confirm from the "
            "workspace/tools, say what you'd need to (a file, a run, a source) "
            "rather than guessing."
        ),
        sources=[SRC_ANTHROPIC_BE_CLEAR, SRC_SIMONW, SRC_CC_BESTPRACTICE],
        check=rule_no_uncertainty_budget,
    ),
    # ---- L4 goals & loops ----
    Rule(
        id="implicit-goal",
        tier=4,
        name="Action without goal",
        nudge=(
            "You said WHAT to do but not WHY. State the goal in one clause "
            "('so that …', 'in order to …', 'because …') — it lets Claude "
            "propose a cheaper means when there is one."
        ),
        guidance=(
            "User's prompt has an action but no stated goal. State your best "
            "guess at the goal in one sentence and check it BEFORE acting; ask "
            "if there's a cheaper way to reach the same goal that skips the "
            "specified means."
        ),
        sources=[SRC_ANTHROPIC_BE_CLEAR, SRC_CC_BESTPRACTICE, SRC_PROMPT_REPORT],
        check=rule_implicit_goal,
    ),
    Rule(
        id="unbounded-iteration",
        tier=4,
        name="Loop without stopping condition",
        nudge=(
            "'Keep improving' or 'refine more' without a stopping condition "
            "burns rounds. Add 'until … passes / matches / is under N lines' "
            "or a max number of iterations."
        ),
        guidance=(
            "User asked for iterative refinement without a stopping condition. "
            "Propose an explicit exit criterion (test passes, rubric hit, N "
            "iterations, no new issues found) BEFORE the first round and "
            "confirm it."
        ),
        sources=[SRC_ANTHROPIC_CHAIN, SRC_PROMPT_REPORT, SRC_SIMONW],
        check=rule_unbounded_iteration,
    ),
    Rule(
        id="no-rubric-for-refine",
        tier=4,
        name="Refinement without rubric",
        nudge=(
            "'Refine this' / 'make it better' without a rubric drifts. Name the "
            "1–3 axes the next pass should improve (clarity, correctness, "
            "brevity) so 'better' isn't a moving target."
        ),
        guidance=(
            "User asked for refinement without saying which axis to improve. "
            "Propose 1–3 named axes; state which axis this pass targets and "
            "which it will NOT change; confirm before iterating."
        ),
        sources=[SRC_ANTHROPIC_BE_CLEAR, SRC_ANTHROPIC_CHAIN, SRC_PROMPT_REPORT],
        check=rule_no_rubric_for_refine,
    ),
    # ---- L5 Claude-Code tool-native ----
    Rule(
        id="no-plan-mode-for-risky",
        tier=5,
        name="Risky change without a plan first",
        nudge=(
            "Migration / delete / rewrite / prod-touching changes usually earn "
            "a plan pass first. Try: 'propose a plan first (don't touch code)' "
            "or invoke plan mode."
        ),
        guidance=(
            "User asked for a risky change without asking for a plan. Before "
            "editing, propose an ordered plan (what changes, what stays, what "
            "the rollback is) and get one line of confirmation before "
            "executing."
        ),
        sources=[SRC_CC_BESTPRACTICE, SRC_CC_HOOKS, SRC_ANTHROPIC_CHAIN],
        check=rule_no_plan_mode_for_risky,
    ),
    Rule(
        id="no-task-list-for-multi-step",
        tier=5,
        name="Multi-step ask without a task list",
        nudge=(
            "Three or more action verbs in one prompt drift into partial work. "
            "Ask for a TaskCreate / checklist first so nothing is silently "
            "dropped."
        ),
        guidance=(
            "User's prompt contains 3+ discrete actions. Use TaskCreate to "
            "materialize the steps up front, mark each in_progress as you "
            "start, and completed as you finish — this makes partial work "
            "visible."
        ),
        sources=[SRC_CC_BESTPRACTICE, SRC_CC_HOOKS],
        check=rule_no_task_list_for_multi_step,
    ),
    Rule(
        id="no-agents-for-parallel-lookup",
        tier=5,
        name="Multiple lookups without parallel agents",
        nudge=(
            "Independent 'find X and also find Y' asks are cheaper as parallel "
            "Agent/Explore calls than sequential greps. Say 'run these in "
            "parallel'."
        ),
        guidance=(
            "User implied multiple independent lookups. Fan them out with "
            "parallel Agent (Explore) calls in a single message rather than "
            "sequential Bash/Grep — same wall-clock, better coverage."
        ),
        sources=[SRC_CC_BESTPRACTICE, SRC_CC_HOOKS],
        check=rule_no_agents_for_parallel_lookup,
    ),
    Rule(
        id="no-role-for-critique",
        tier=5,
        name="Review ask without a role",
        nudge=(
            "'Review my X' is stronger when you invoke a role: /roles:as "
            "reviewer, or ask for a skeptic pass, security review, adversarial "
            "check. The persona shapes what gets caught."
        ),
        guidance=(
            "User asked for a review without specifying a persona. Ask which "
            "lens (correctness / security / API / readability / performance) — "
            "then invoke or emulate that role explicitly rather than doing a "
            "generic pass."
        ),
        sources=[SRC_CC_BESTPRACTICE, SRC_ANTHROPIC_CHAIN, SRC_SIMONW],
        check=rule_no_role_for_critique,
    ),
    Rule(
        id="no-panel-for-contested-design",
        tier=5,
        name="Contested design without a panel",
        nudge=(
            "Signals of a genuine design fork ('which is better', 'torn "
            "between', 'tradeoff'). Consider /brainstorm-panel with 3–4 "
            "perspectives — one Claude reasoning solo tends to anchor."
        ),
        guidance=(
            "User signaled a contested design choice. Before answering, name "
            "2–3 lenses that could disagree (skeptic / architect / user); if "
            "they'd genuinely diverge, offer to run the panel; if not, note "
            "why they wouldn't and answer directly."
        ),
        sources=[SRC_ANTHROPIC_CHAIN, SRC_PROMPT_REPORT, SRC_CC_BESTPRACTICE],
        check=rule_no_panel_for_contested_design,
    ),
    Rule(
        id="no-workflow-for-fanout",
        tier=5,
        name="Fan-out ask without Workflow",
        nudge=(
            "'For each of these 20+ things …' as one prompt is a serial slog. "
            "Consider Workflow or parallel agents so the fan-out actually "
            "fans out."
        ),
        guidance=(
            "User implied fan-out over many items. Propose parallel agent "
            "fan-out or Workflow orchestration BEFORE starting; a serial for-"
            "each loop should be the fallback, not the default."
        ),
        sources=[SRC_CC_BESTPRACTICE, SRC_CC_HOOKS],
        check=rule_no_workflow_for_fanout,
    ),
    # ---- L6 skill-awareness ----
    Rule(
        id="no-skill-lookup",
        tier=6,
        name='"How do I …" without checking existing skills',
        nudge=(
            "That reads like a pattern that might already have a skill. "
            "Before rolling your own: ask 'is there a skill for this?' — "
            "or list the catalog with /help. Discoverability > memorability."
        ),
        guidance=(
            "User asked 'how do I X' / 'what's the standard way' without "
            "checking whether an existing skill covers it. Before answering, "
            "briefly note whether any installed skill/plugin is a plausible "
            "fit (roles, dev-crew, brainstorm-panel, research-sweep, "
            "screenshot-tour, tune-repo, etc.). If yes, offer to invoke it. "
            "If no, proceed with a direct answer."
        ),
        sources=[SRC_NORMAN_DESIGN, SRC_ANTHROPIC_SKILLS, SRC_CC_BESTPRACTICE],
        check=rule_no_skill_lookup,
    ),
    Rule(
        id="pattern-worth-abstracting",
        tier=6,
        name="Repetition without abstraction",
        nudge=(
            "You said 'again' / 'same as before'. Rule of three: on the "
            "third occurrence a pattern earns a skill. Worth naming, "
            "extracting, or asking for a skill scaffold now?"
        ),
        guidance=(
            "User signaled repetition ('again', 'yet another', 'same as "
            "last time'). Note the repetition and — if we're at N≥3 — ask "
            "whether they want to extract this into a reusable skill / "
            "template / slash-command. Don't force it on N=2; YAGNI."
        ),
        sources=[SRC_FOWLER_REFACTOR, SRC_KENT_BECK_YAGNI, SRC_ANTHROPIC_SKILLS],
        check=rule_pattern_worth_abstracting,
    ),
    Rule(
        id="no-skill-composition",
        tier=6,
        name="Repeatable ceremony not named as a skill",
        nudge=(
            "You described a multi-step process meant to be repeated. That's "
            "the shape of a skill — name → steps → done → sources. Worth "
            "codifying so you don't re-derive the sequence?"
        ),
        guidance=(
            "User described a repeatable multi-step workflow ('first X, then "
            "Y, then Z', 'every time we do this…'). Offer to draft a skill "
            "scaffold (SKILL.md with frontmatter, steps, verification). Point "
            "at the alexmskills patterns if the user has that plugin family."
        ),
        sources=[SRC_MCILROY_UNIX, SRC_ANTHROPIC_SKILLS, SRC_FOWLER_REFACTOR],
        check=rule_no_skill_composition,
    ),
]

RULES_BY_ID = {r.id: r for r in RULES}
RULE_ORDER = [r.id for r in RULES]  # tier-then-declaration order


# ---------------------------------------------------------------------------
# Positive catalog — praise the SPECIFIC positive behavior, not absence of
# a negative. Sparing, specific, and process-focused per Brophy 1981, Mueller
# & Dweck 1998, Fogg 2019, Deci & Ryan 2000; Kohn 1993 for the "don't dilute"
# principle (never praise + nudge on the same prompt).
# ---------------------------------------------------------------------------


@dataclass
class Positive:
    id: str                            # mirrors a negative rule where useful
    mirrors: str                       # rule id it corresponds to (for first-after-fire)
    tier: int
    check: Callable[[str], bool]
    praises: list[str]                 # 2–3 phrasings, rotated for novelty
    sources: list[tuple[str, str]]


# ---- L1 positives ----------------------------------------------------------

def pos_explicit_definition_of_done(prompt: str) -> bool:
    if not _starts_with_action(prompt):
        return False
    pl = prompt.lower()
    return bool(re.search(
        r"\b(until |verify|test\w* pass|passes ci|expect|assert|"
        r"green build|so that|output should|should return|no errors?)\b", pl))


def pos_scoped_scope(prompt: str) -> bool:
    pl = prompt.lower()
    unbounded = re.search(r"\b(all|every|entire|the whole)\b", pl)
    action = re.search(r"\b(refactor|rewrite|update|rename|remove|migrate|touch)\b", pl)
    limiter = re.search(
        r"\b(only|except|under\s+\S+|in\s+\S+|matching|starting with|"
        r"whose|where|within|limited to|scoped to)\b", pl)
    return bool(unbounded and action and limiter)


def pos_stated_metric(prompt: str) -> bool:
    pl = prompt.lower()
    fuzzy = re.search(r"\b(better|improved?|faster|smaller|cleaner|smoother)\b", pl)
    metric = re.search(
        r"\b\d+\s*(%|ms|s|second|seconds|kb|mb|x)|by \d|under \d|"
        r"passes .* test|assert|matches|from \d.*to \d", pl)
    return bool(fuzzy and metric)


def pos_stated_guardrails(prompt: str) -> bool:
    pl = prompt.lower()
    heavy = re.search(
        r"\b(refactor|rewrite|migrate|move|rename|delete|remove|replace)\b", pl)
    guard = re.search(
        r"(don'?t\s+|do\s+not\s+|must\s+not|without\s+(breaking|changing|touching)|"
        r"keep\s+.*\s+(stable|intact|unchanged|as\s+is|working)|"
        r"preserve|no\s+changes?\s+to|backwards[- ]compatible|api[- ]compatible)", pl)
    return bool(heavy and guard)


# ---- L2 positives ----------------------------------------------------------

def pos_stated_verify_loop(prompt: str) -> bool:
    if not _starts_with_action(prompt):
        return False
    pl = prompt.lower()
    return bool(re.search(
        r"\b(run\s+tests?|verify|check\s+that|make\s+sure|confirm|"
        r"assert|expect|passes\s+ci|green\s+build)\b", pl))


def pos_cited_context(prompt: str) -> bool:
    """Fires when the prompt grounds itself in a specific artifact.
    v0.8.0: loosened from "role reference AND ID" to "any concrete
    grounding present" — real substantive prompts cite files, ticket
    IDs, project names without a 'the failing test' style role phrase.
    Evidence: v0.7.0 log had "file tickets for RFJ-070" (specific ID),
    "add both sections to ENGINE-COMPARISON.adoc" (file with ext),
    "Check latest changes to notify4j" (specific project) — all should
    have praised, none did."""
    ids = re.search(
        # ticket-style ids (RFJ-070, JIRA-1234, #123)
        r"\b[A-Z]{2,}-\d+\b|#\d+|\bpr\s+\d+\b|"
        # test-method paths (pytest::method)
        r"\btest\w*\s+\w+::\w+\b|"
        # backticked identifiers (`--flag`, `class Foo`)
        r"`[^`]+`|"
        # URLs
        r"https?://|"
        # explicit file paths with extension
        r"\b[\w./-]+\.(py|js|ts|tsx|jsx|java|kt|go|rs|md|json|yaml|yml|sh|"
        r"toml|adoc|rst|html|css|scss|sql|xml|proto|conf|env|txt|log)\b|"
        # path-with-slash reference (src/foo/bar)
        r"\b(src|test|tests|lib|app|config|docs?|scripts?|bin)/[\w./-]+\b|"
        # tech-name identifier — lowercase word ending in digit(s),
        # min 4 letters (notify4j, redis7, python3, spring5) OR
        # hyphenated identifier of 3+3 letters (spring-boot, react-router)
        r"\b[a-z]{4,}\d+[a-z]*\b|\b[a-z]{3,}-[a-z]{3,}(-[a-z]+)*\b",
        prompt,
    )
    return bool(ids)


def pos_grounded_scope(prompt: str) -> bool:
    """Fires when a prompt names a specific target — a project, a file
    stem, a config key, a component — rather than a vague 'this' or
    'the thing'. Complement to no-vague-reference from the *positive*
    side. v0.8.0."""
    # Must be a substantive prompt (not just a filepath). At least 4 words.
    if len(prompt.split()) < 4:
        return False
    # Presence of any concrete grounding wins.
    return pos_cited_context(prompt)


def pos_stated_format(prompt: str) -> bool:
    pl = prompt.lower()
    ask = re.search(
        r"\b(give\s+me|show\s+me|list|summari[sz]e|generate|produce|write)\b"
        r".{0,40}\b(summary|report|answer|list|table|analysis|breakdown|overview|plan)\b",
        pl)
    shape = re.search(
        r"\b(bullet|table|json|markdown|paragraph|numbered|"
        r"\d+\s*(items?|points?|rows?|bullets?|paragraphs?)|"
        r"columns?|rows?|schema|section|per\s+\w+|under\s+\d+\s+words?)\b", pl)
    return bool(ask and shape)


# ---- L3 positives ----------------------------------------------------------

def pos_provided_example(prompt: str) -> bool:
    pl = prompt.lower()
    pattern = re.search(
        r"\b(like|similar to|in the style of|matching|same pattern|"
        r"same as|following the same|analogous to)\b", pl)
    example = re.search(
        r"```|for example|e\.g\.|for instance|"
        r"\b(example|sample|input|output|given)\s*[:\-]",
        prompt, re.IGNORECASE)
    return bool(pattern and example)


def pos_asked_think_first(prompt: str) -> bool:
    pl = prompt.lower()
    hard = re.search(
        r"\b(why does|why doesn.?t|debug|diagnose|figure out|"
        r"trace|root cause|reason about|analyz\w+ (this|the|these))\b", pl)
    think = re.search(
        r"\b(think|reason|work through|step by step|"
        r"before (you )?answer|show your (work|reasoning)|"
        r"first .* then|plan .* first)\b", pl)
    return bool(hard and think)


def pos_provided_rubric(prompt: str) -> bool:
    pl = prompt.lower()
    judge = re.search(
        r"\b(is this(?:\s+\w+){0,3}\s+(good|correct|ok|fine|right|acceptable)|"
        r"rate this|rank these|which is better|assess|evaluate|grade this)\b", pl)
    rubric = re.search(
        r"\b(rubric|criteria|dimensions?|axis|axes|"
        r"scored on|graded on|based on:|"
        r"on\s+(correctness|performance|readability|simplicity|"
        r"safety|rollback|clarity))\b", pl)
    return bool(judge and rubric)


def pos_stated_uncertainty_budget(prompt: str) -> bool:
    pl = prompt.lower()
    investigative = re.search(
        r"\b(find (out|whether)|figure out|investigate|search for|"
        r"locate|identify|determine|is there|are there)\b", pl)
    uncertainty = re.search(
        r"(if (you'?re |you are )?(unsure|not sure|uncertain|unclear)|"
        r"when in doubt|if you can'?t|otherwise say so|flag if|admit if)", pl)
    return bool(investigative and uncertainty)


# ---- L4 positives ----------------------------------------------------------

def pos_stated_goal(prompt: str) -> bool:
    """v0.8.0: also matches reason clauses ('we are fully moved away',
    'we already migrated', 'the plan is …') that state the WHY in a
    natural voice rather than the textbook 'so that' / 'in order to'."""
    if not _starts_with_action(prompt):
        return False
    pl = prompt.lower()
    return bool(re.search(
        r"(\bso that\b|\bbecause\b|\bgoal is\b|\bgoal:|"
        r"\bin order to\b|\bto (make|enable|allow|support|prevent|"
        r"fix|reduce|increase|avoid|unblock|match)\b|"
        r"\bwe want to\b|\bthe point is\b|\bwhy: |"
        # v0.8.0 additions — real natural-voice reason clauses
        r"\bwe (are|have|were|already) (moved|migrated|decided|"
        r"switched|dropped|retired)\b|"
        r"\bfully (moved|migrated|switched) (away|to|from)\b|"
        r"\bthe plan is\b|\bthe ask is\b|"
        r"\bfor (the |the next |the upcoming )?(release|ci|prod|q\d))",
        pl))


def pos_bounded_iteration(prompt: str) -> bool:
    pl = prompt.lower()
    loop = re.search(
        r"\b(keep (going|improving|refining|iterating)|"
        r"iterate on|polish more|refine|another pass|another round)\b", pl)
    stop = re.search(
        r"\b(until|when|once|stop when|target:|goal:|score of|"
        r"passes|matches|below \d|under \d|no more \w+|at most \d)\b", pl)
    return bool(loop and stop)


# ---- L5 positives ----------------------------------------------------------

def pos_asked_plan_first(prompt: str) -> bool:
    pl = prompt.lower()
    risky = re.search(
        r"\b(migrate|migration|schema change|drop (table|column)|"
        r"rewrite the (module|package|whole)|"
        r"refactor the (whole|entire|core)|breaking change|"
        r"deploy to prod|production data|change the api)\b", pl)
    plan = re.search(
        r"\b(plan|propose|design|outline|approach|strategy|"
        r"dry.?run|preview|plan mode|before (doing|touching|editing))\b", pl)
    return bool(risky and plan)


def pos_asked_task_list(prompt: str) -> bool:
    pl = prompt.lower()
    verbs = "|".join(ACTION_VERBS)
    step_count = len(re.findall(rf"\b(?:{verbs})\b", pl))
    if step_count < 3:
        return False
    return bool(re.search(
        r"\b(task list|todo|todos|track progress|break it down|"
        r"checklist|steps?:|use taskcreate|plan\b)\b", pl))


def pos_asked_parallel(prompt: str) -> bool:
    pl = prompt.lower()
    multi = re.search(
        r"\b(and also (find|check|look|search|verify)|"
        r"search for .* and .* and|"
        r"look up .* and .*|both .* and .*)\b", pl)
    parallel = re.search(
        r"\b(in parallel|concurrent|fan[- ]out|agents?|subagents?|"
        r"explore|multiple lookups|separate agents)\b", pl)
    return bool(multi and parallel)


def pos_invoked_role(prompt: str) -> bool:
    pl = prompt.lower()
    critique = re.search(
        r"\b(review this|review my|code review|critique|"
        r"find issues|find bugs|check my|look over|red[- ]team)\b", pl)
    role = re.search(
        r"/roles:as|/roles:|/brainstorm|/panel|/review-agents|"
        r"\breviewer\b|\bskeptic\b|security[- ]review|adversarial|"
        r"as a \w+ engineer|from .* perspective", pl)
    return bool(critique and role)


def pos_asked_panel(prompt: str) -> bool:
    pl = prompt.lower()
    fork = re.search(
        r"\b(should i (use|do|pick|go with)|which is better|"
        r"which one (should|would)|debate|trade[- ]?off|"
        r"option a.*option b|torn between|weighing)\b", pl)
    panel = re.search(
        r"\b(panel|brainstorm|multiple perspectives?|opposing views?|"
        r"steelman|/brainstorm|/panel|adversarial review)\b", pl)
    return bool(fork and panel)


def pos_invoked_skill(prompt: str) -> bool:
    """User reached for an existing skill by name."""
    pl = prompt.lower()
    slash = re.search(r"/[a-z0-9\-]+(?::[a-z0-9\-]+)?\b", pl)
    named = re.search(
        r"\buse (the|our) [a-z\-]+ (skill|plugin|command)\b|"
        r"\bthe [a-z\-]+ (skill|plugin) can\b|"
        r"\brun (/[a-z0-9\-]+|the [a-z\-]+ (skill|command))\b|"
        r"\binvoke .* skill\b", pl)
    return bool(slash or named)


def pos_abstracted_to_skill(prompt: str) -> bool:
    """User named a repeatable pattern and moved to abstract it."""
    pl = prompt.lower()
    return bool(re.search(
        r"\b(let'?s make (a|this|it) (a )?skill|"
        r"extract (this|it) (in)?to a skill|"
        r"this (should be|deserves|feels like) a skill|"
        r"turn (this|it) into a skill|"
        r"create a skill for|"
        r"codif(y|ies) this (as|into) a skill)\b", pl))


def pos_asked_workflow(prompt: str) -> bool:
    pl = prompt.lower()
    fanout = re.search(
        r"\b(for each|across (all|every|these)|iterate over|"
        r"one by one|do this (to|for) (all|every|each))\b", pl)
    counted = re.search(
        r"\b([5-9]|1\d|2\d|3\d|4\d|5\d|\d{3,})\s+"
        r"(files|items|repos|entries|records|rows|things|"
        r"tests|packages|modules|targets|methods|classes|projects)\b", pl)
    tool = re.search(
        r"\b(workflow|fan[- ]out|parallel|agents?|/workflow|ultracode|pipeline)\b", pl)
    return bool(fanout and counted and tool)


# Praise phrasings: one specific/process-focused + one warm/humorous per positive.
# Rotated to prevent habituation.
POSITIVES: list[Positive] = [
    Positive("explicit-definition-of-done", "no-definition-of-done", 1,
             pos_explicit_definition_of_done, [
                 "You named the acceptance criteria — that's the single biggest lever on 'did this actually succeed'.",
                 "Definition of done stated up front. Somewhere, a QA engineer wipes away a tear.",
             ], [SRC_BROPHY_PRAISE, SRC_MUELLER_DWECK]),
    Positive("scoped-scope", "unbounded-scope", 1,
             pos_scoped_scope, [
                 "'All / every X — but only Y'. That's the difference between a refactor and a rewrite-of-the-wrong-module.",
                 "You bounded the unbounded word. Scalpel, not sledgehammer.",
             ], [SRC_BROPHY_PRAISE, SRC_FOGG_TINY]),
    Positive("stated-metric", "improve-without-metric", 1,
             pos_stated_metric, [
                 "You attached a number to 'better'. 'Success' now has a target instead of a vibe.",
                 "'Faster' plus a metric. Physics can help you now.",
             ], [SRC_MUELLER_DWECK, SRC_DECI_RYAN]),
    Positive("stated-guardrails", "missing-guardrails", 1,
             pos_stated_guardrails, [
                 "You stated the invariant. That single 'don't touch X' line prevents entire classes of regression.",
                 "You named what must stay stable. Future-you is thankful (and probably raises a beer).",
             ], [SRC_BROPHY_PRAISE, SRC_FOGG_TINY]),
    # L2
    Positive("stated-verify-loop", "no-verify-loop", 2,
             pos_stated_verify_loop, [
                 "Change plus verification in one prompt. That's the whole loop, closed.",
                 "'Implement X and confirm the tests pass.' Chef's kiss.",
             ], [SRC_BROPHY_PRAISE, SRC_DECI_RYAN]),
    Positive("cited-context", "missing-context-fetch", 2,
             pos_cited_context, [
                 "You cited the specific test / PR / error text. Hallucination surface: zero.",
                 "You named the thing instead of 'the thing'. Ambiguity: minus one.",
             ], [SRC_BROPHY_PRAISE, SRC_MUELLER_DWECK]),
    Positive("grounded-scope", "vague-reference", 1,
             pos_grounded_scope, [
                 "You grounded the ask in a specific file / id / project. Single biggest ambiguity killer.",
                 "Concrete pointer in the prompt itself beats 'the thing' every time — Claude knows exactly what to touch.",
             ], [SRC_BROPHY_PRAISE, SRC_ANTHROPIC_BE_CLEAR]),
    Positive("stated-format", "no-format-spec", 2,
             pos_stated_format, [
                 "Format specified up front — you'll get what you actually wanted, not a wall of text.",
                 "You told the output what shape to be. It'll go there.",
             ], [SRC_BROPHY_PRAISE, SRC_FOGG_TINY]),
    # L3
    Positive("provided-example", "no-few-shot", 3,
             pos_provided_example, [
                 "You showed an exemplar. Few-shot beats description most days of the week.",
                 "'Like this ↓' beats 'like this ↑' every time.",
             ], [SRC_MUELLER_DWECK, SRC_BROPHY_PRAISE]),
    Positive("asked-think-first", "no-chain-of-thought", 3,
             pos_asked_think_first, [
                 "You asked Claude to reason before answering. That's a documented accuracy lift on hard questions.",
                 "'Think first, then answer.' Simple, cheap, effective — like decaf but for reasoning.",
             ], [SRC_MUELLER_DWECK, SRC_DECI_RYAN]),
    Positive("provided-rubric", "no-rubric", 3,
             pos_provided_rubric, [
                 "You gave a rubric. 'Is this good?' now has a shape and a scale.",
                 "You named the axes. 'Good' just became measurable.",
             ], [SRC_BROPHY_PRAISE, SRC_DECI_RYAN]),
    Positive("stated-uncertainty-budget", "no-uncertainty-budget", 3,
             pos_stated_uncertainty_budget, [
                 "You left space for 'I don't know' as an answer. That prevents confident guesses that read as facts.",
                 "You told Claude it's okay to admit uncertainty. A rare and useful gift.",
             ], [SRC_DECI_RYAN, SRC_KOHN_REWARDS]),
    # L4
    Positive("stated-goal", "implicit-goal", 4,
             pos_stated_goal, [
                 "Goal stated — now a cheaper means is on the table if one exists.",
                 "You said WHY not just WHAT. This unlocks the good stuff.",
             ], [SRC_DECI_RYAN, SRC_DWECK_MINDSET]),
    Positive("bounded-iteration", "unbounded-iteration", 4,
             pos_bounded_iteration, [
                 "You set a stopping condition. The loop knows when to exit — no infinite polishing.",
                 "Iteration + exit criterion. That's the difference between refinement and Zeno's paradox.",
             ], [SRC_FOGG_TINY, SRC_BROPHY_PRAISE]),
    # L5 tool-native
    Positive("asked-plan-first", "no-plan-mode-for-risky", 5,
             pos_asked_plan_first, [
                 "Risky change plus 'plan first'. You just avoided the 'oops I changed everything' timeline.",
                 "You asked for a plan before touching prod. Excellent survival instinct.",
             ], [SRC_BROPHY_PRAISE, SRC_FOGG_TINY]),
    Positive("asked-task-list", "no-task-list-for-multi-step", 5,
             pos_asked_task_list, [
                 "You asked for a task list on a multi-step ask. Partial work is now visible instead of forgotten.",
                 "TaskCreate for the win. Half-finished work has fewer places to hide.",
             ], [SRC_BROPHY_PRAISE, SRC_FOGG_TINY]),
    Positive("asked-parallel", "no-agents-for-parallel-lookup", 5,
             pos_asked_parallel, [
                 "You asked for parallel agents on independent lookups. Wall-clock will thank you.",
                 "Fanning out instead of serializing. The CPU cores are cheering.",
             ], [SRC_MUELLER_DWECK, SRC_BROPHY_PRAISE]),
    Positive("invoked-role", "no-role-for-critique", 5,
             pos_invoked_role, [
                 "You named the review lens. Different personas catch different things — the ask is now sharp.",
                 "You put on a specific hat instead of a generic one. Reviews improve accordingly.",
             ], [SRC_BROPHY_PRAISE, SRC_DECI_RYAN]),
    Positive("asked-panel", "no-panel-for-contested-design", 5,
             pos_asked_panel, [
                 "You reached for the panel on a real design fork. Solo Claude anchors; a panel doesn't.",
                 "Multiple perspectives on a contested call. Groupthink: dispatched.",
             ], [SRC_DECI_RYAN, SRC_BROPHY_PRAISE]),
    Positive("asked-workflow", "no-workflow-for-fanout", 5,
             pos_asked_workflow, [
                 "You reached for Workflow / parallel agents on a fan-out. That's not a for-loop, that's the whole show.",
                 "Fan-out with parallelism. You made 30 things fit in one thing's time budget.",
             ], [SRC_MUELLER_DWECK, SRC_FOGG_TINY]),
    # ---- L6 skill-awareness positives ----
    Positive("invoked-skill", "no-skill-lookup", 6,
             pos_invoked_skill, [
                 "You reached for an existing skill instead of re-deriving. Composition wins — this is what the plugin catalog is for.",
                 "You used the skill instead of describing what the skill does. Efficient.",
             ], [SRC_MCILROY_UNIX, SRC_NORMAN_DESIGN, SRC_ANTHROPIC_SKILLS]),
    Positive("abstracted-to-skill", "pattern-worth-abstracting", 6,
             pos_abstracted_to_skill, [
                 "You noticed a repeatable pattern and moved to abstract it. That's the rule-of-three payoff.",
                 "Pattern → skill on the same day you noticed it. Future-you owes present-you a beer.",
             ], [SRC_FOWLER_REFACTOR, SRC_KENT_BECK_YAGNI, SRC_ANTHROPIC_SKILLS]),
]

POSITIVES_BY_ID = {p.id: p for p in POSITIVES}
POSITIVES_BY_MIRROR = {p.mirrors: p for p in POSITIVES}

# Milestone phrasings — used when a rule graduates to 'mastered' or when a
# user does the positive thing on the prompt right after being nudged.
MASTERY_PHRASINGS = [
    "🎉 Rule mastered: **{rule_name}**. That's {threshold} clean prompts in a row — the coach retires this one. Next up: **{next_name}**.",
    "Level up: **{rule_name}** is now habitual. Coach fades on this one; the next-tier rule steps in ({next_name}).",
    "🏁 Graduated: **{rule_name}**. You outgrew this nudge. Turning it off; welcoming **{next_name}** into the rotation.",
]

FIRST_AFTER_FIRE_PHRASINGS = [
    "✨ You just did the exact thing you were nudged about last prompt (**{rule_name}**). That's how the pattern actually locks in.",
    "Immediate correction on **{rule_name}** — that follow-through is where habits form (Fogg's tiny-habits model in action).",
    "One-shot correction on **{rule_name}**. This is the highest-leverage moment in the whole coaching loop.",
]

ENCOURAGEMENT_SOURCES = [
    SRC_MUELLER_DWECK, SRC_DWECK_MINDSET, SRC_FOGG_TINY,
    SRC_BROPHY_PRAISE, SRC_DECI_RYAN, SRC_KOHN_REWARDS,
]

# ---------------------------------------------------------------------------
# State + config IO
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return dict(default)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return dict(default)
        return data
    except (OSError, json.JSONDecodeError):
        return dict(default)


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=False), encoding="utf-8")
    tmp.replace(path)


def resolve_config(cwd: Path) -> dict:
    local_cfg = load_json(cwd / ".claude" / "prompt-coach" / "config.json", {})
    global_cfg = load_json(GLOBAL_CONFIG, {})
    merged = dict(DEFAULT_CONFIG)
    merged.update({k: v for k, v in global_cfg.items() if v is not None})
    merged.update({k: v for k, v in local_cfg.items() if v is not None})
    return merged


def blank_global_state() -> dict:
    return {
        "version": 1,
        "prompt_count": 0,
        "rules": {},   # rule_id -> {status, fires_total, clean_streak, last_fired_at, last_nudged_at, graduated_at}
        # Health / self-report metrics. Rising numbers here signal the regex
        # rules aren't covering the user's real prompts and it's worth
        # tuning (or enabling the LLM fallback when built).
        "normalization_stats": {
            "prompts_with_corrections": 0,
            "tokens_corrected_total": 0,
            "top_corrections": {},   # original → count
        },
        "llm_fallback_stats": {
            "calls_total": 0,
            "fired_rules_via_fallback": 0,
        },
    }


def blank_local_state() -> dict:
    return {
        "version": 1,
        "prompt_count": 0,
        "reactivated": [],
        "last_nudge_prompt": 0,
        "rules": {},   # rule_id -> {fires_here, clean_streak_here, last_fired_at, last_nudged_at}
    }


# ---------------------------------------------------------------------------
# Rule scoring & selection
# ---------------------------------------------------------------------------


def effective_status(rule_id: str, g: dict, l: dict) -> str:
    if rule_id in l.get("reactivated", []):
        return "practicing"
    entry = g.get("rules", {}).get(rule_id, {})
    return entry.get("status", "dormant")


def active_rules_split(cfg: dict, g: dict, l: dict) -> tuple[list[str], list[str]]:
    """v0.9.0: split into (practicing, mastered). Practicing is capped at
    max_active_rules (the tier that drives daily coaching). Mastered is
    uncapped — they always evaluate, but emit rarely via a longer cooldown.
    A cooldown of 0 disables mastered firing entirely."""
    practicing: list[str] = []
    mastered: list[str] = []
    for rid in RULE_ORDER:
        if rid in cfg.get("disabled_rules", []):
            continue
        st = effective_status(rid, g, l)
        if st == "mastered":
            mastered.append(rid)
        else:
            practicing.append(rid)
    max_active = int(cfg.get("max_active_rules", 5))
    if len(practicing) > max_active:
        def rank(rid: str) -> tuple:
            r = RULES_BY_ID[rid]
            fires = g.get("rules", {}).get(rid, {}).get("fires_total", 0)
            return (r.tier, -fires, RULE_ORDER.index(rid))
        practicing.sort(key=rank)
        practicing = practicing[:max_active]
    # If mastered firing is disabled, return no mastered candidates.
    if int(cfg.get("mastered_cooldown_prompts", 50)) <= 0:
        mastered = []
    return practicing, mastered


def active_rule_ids(cfg: dict, g: dict, l: dict) -> list[str]:
    """Back-compat: return practicing only (used where the split isn't needed)."""
    practicing, _ = active_rules_split(cfg, g, l)
    return practicing


def fires(prompt: str, rule_id: str) -> bool:
    return RULES_BY_ID[rule_id].check(prompt)


def within_cooldown(rid: str, l: dict, cfg: dict, mastered: bool = False) -> bool:
    last = l.get("rules", {}).get(rid, {}).get("last_nudged_prompt")
    if last is None:
        return False
    key = "mastered_cooldown_prompts" if mastered else "cooldown_prompts"
    default = 50 if mastered else 5
    return (l.get("prompt_count", 0) - last) < int(cfg.get(key, default))


def pick_nudge(fired: list[str], l: dict, cfg: dict, mastered: bool = False) -> str | None:
    """Pick the highest-priority firing rule that isn't in cooldown.
    mastered=True uses the longer mastered_cooldown_prompts window."""
    eligible = [r for r in fired if not within_cooldown(r, l, cfg, mastered=mastered)]
    if not eligible:
        return None
    def rank(rid: str) -> tuple:
        r = RULES_BY_ID[rid]
        return (r.tier, RULE_ORDER.index(rid))
    eligible.sort(key=rank)
    return eligible[0]


# ---------------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------------


def _refresher_box(rule: Rule, days_since_mastery: int | None, mode: str) -> str:
    """v0.9.0 — softer box for a mastered rule that fired. No sources,
    no progress bar; a one-line refresher plus the context that this rule
    is mastered."""
    mastery_line = (f"mastered {days_since_mastery}d ago"
                    if days_since_mastery is not None else "mastered")
    return (
        f"🔄 prompt-coach [{mode} · refresher] — {rule.id} ({mastery_line})\n"
        f"   {rule.nudge}"
    )


def _box(rule: Rule, streak: int, threshold: int, mode: str) -> str:
    bar = "━" * 70
    lines = [
        bar,
        f"🎯 prompt-coach [{mode}] — {rule.id}: {rule.name}",
        "",
        rule.nudge,
        "",
        "Sources:",
    ]
    for title, url in rule.sources:
        lines.append(f"  • {title}  <{url}>")
    lines.append("")
    lines.append(
        f"Progress: {streak}/{threshold} clean prompts → mastered · "
        f"say 'coach pause 10' to silence · 'coach off {rule.id}' to disable."
    )
    lines.append(bar)
    return "\n".join(lines)


def _context_for_claude(rule: Rule) -> str:
    return (
        f"[prompt-coach] The user's prompt matched the coaching rule "
        f"'{rule.id}' ({rule.name}). Guidance for how to respond well: "
        f"{rule.guidance} This is advisory, not a directive — proceed with "
        f"the user's actual task."
    )


def _inline_context_for_claude(rule: Rule, streak: int, threshold: int) -> str:
    """v0.10.0 — `nudge_style: inline` variant. Instructs Claude to render
    the nudge as a visible block at the start of its response so the user
    sees the coaching inline. More visible than stderr; costs ~50 output
    tokens per fire."""
    bar = "━" * 60
    box = (
        f"{bar}\n"
        f"🎯 prompt-coach — {rule.id}: {rule.name}\n\n"
        f"{rule.nudge}\n\n"
        f"Progress: {streak}/{threshold} clean prompts → mastered\n"
        f"{bar}"
    )
    return (
        f"[prompt-coach · inline mode] The user's prompt matched the "
        f"coaching rule '{rule.id}' ({rule.name}). Because the user has "
        f"opted into `nudge_style: inline`, render the following block "
        f"AT THE VERY START of your response, VERBATIM, before addressing "
        f"the user's task:\n\n"
        f"{box}\n\n"
        f"Then answer the user's actual question. If the nudge doesn't "
        f"substantively apply because prior context makes the referent "
        f"clear, still render the block but add a one-line note like "
        f"'(context resolves the ambiguity, proceeding)' after it. "
        f"Guidance for shaping the response: {rule.guidance}"
    )


def _inline_context_for_claude_refresher(rule: Rule, days_since: int | None) -> str:
    """v0.10.0 — inline variant for a refresher (mastered rule that fired).
    Softer instruction — one-line block, not the full-width box."""
    mastery_line = (f"mastered {days_since}d ago"
                    if days_since is not None else "mastered")
    line = f"🔄 prompt-coach — refresher on {rule.id} ({mastery_line}) — {rule.nudge}"
    return (
        f"[prompt-coach · inline refresher] Mastered rule '{rule.id}' matched. "
        f"Render this ONE line at the start of your response before addressing "
        f"the task: `{line}`. Keep it as a single blockquote or callout line. "
        f"Guidance: {rule.guidance} Don't belabor it — this is a light "
        f"re-fire, not a full nudge."
    )


def _praise_box(kind: str, header: str, text: str,
                sources: list[tuple[str, str]], mode: str) -> str:
    """Praise line — deliberately shorter/gentler than the nudge box."""
    icon = {"mastery": "🎓", "first-after-fire": "✨",
            "variable-ratio": "✅"}.get(kind, "✅")
    lines = [
        f"{icon} prompt-coach [{mode} · {kind}] — {header}",
        f"   {text}",
    ]
    if sources:
        titles = ", ".join(t for t, _ in sources[:2])
        lines.append(f"   (Encouragement grounded in: {titles})")
    return "\n".join(lines)


def _praise_context(kind: str, id_: str, text: str) -> str:
    return (
        f"[prompt-coach · {kind}] The user's prompt did the specific positive "
        f"thing tracked by '{id_}'. Text shown to the user: {text} "
        f"Advisory context; keep the response focused on their actual task."
    )


def pick_praise(positive_fires: list[str], mastery_events: list[str],
                l: dict, g: dict, cfg: dict, nudged_this_prompt: bool
                ) -> tuple[str, str, str, list[tuple[str, str]]] | None:
    """Decide whether (and how) to praise. Never runs on a nudged prompt.

    Priority order (one emit per prompt): mastery > first-after-fire > variable-ratio.
    Returns (kind, id, praise_text, sources) or None.
    """
    if nudged_this_prompt or cfg.get("disable_praise", False):
        return None

    # 1) Mastery celebration — a rule just graduated this prompt.
    if cfg.get("praise_on_mastery", True) and mastery_events:
        rid = mastery_events[0]
        rule = RULES_BY_ID.get(rid)
        # Find next-up rule (still practicing, lowest tier, first in order).
        next_rid = next(
            (r.id for r in RULES
             if g.get("rules", {}).get(r.id, {}).get("status") != "mastered"
             and r.id != rid
             and r.id not in cfg.get("disabled_rules", [])),
            None,
        )
        next_name = RULES_BY_ID[next_rid].name if next_rid else "—"
        idx = int(g.get("praise_count", 0)) % len(MASTERY_PHRASINGS)
        text = MASTERY_PHRASINGS[idx].format(
            rule_name=rule.name if rule else rid,
            threshold=cfg.get("graduation_threshold", 15),
            next_name=next_name,
        )
        return "mastery", rid, text, ENCOURAGEMENT_SOURCES[:2]

    # 2) First-after-fire — user did the positive thing immediately after
    #    being nudged on the mirror rule last prompt.
    last_fired = set(l.get("last_prompt_fired_rules", []) or [])
    if cfg.get("praise_on_first_after_fire", True) and last_fired:
        for pid in positive_fires:
            p = POSITIVES_BY_ID[pid]
            if p.mirrors in last_fired:
                idx = int(g.get("praise_count", 0)) % len(FIRST_AFTER_FIRE_PHRASINGS)
                mirror_name = RULES_BY_ID[p.mirrors].name if p.mirrors in RULES_BY_ID else p.mirrors
                text = FIRST_AFTER_FIRE_PHRASINGS[idx].format(rule_name=mirror_name)
                return "first-after-fire", pid, text, p.sources

    # 3) Variable-ratio — every Nth clean prompt with at least one positive.
    ratio = max(1, int(cfg.get("praise_ratio", 10)))
    clean_count = int(l.get("clean_prompts_since_praise", 0))
    if positive_fires and clean_count >= ratio:
        # Rotate through positive_fires so different behaviors get recognized.
        idx = int(g.get("praise_count", 0)) % len(positive_fires)
        pid = positive_fires[idx]
        p = POSITIVES_BY_ID[pid]
        # Rotate phrasings to avoid habituation.
        p_pr = p.praises
        phrase_idx = int(g.get("praise_count", 0)) % len(p_pr)
        text = p_pr[phrase_idx]
        return "variable-ratio", pid, text, p.sources

    return None


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def _flag_previous_for_review(local_dir: Path, mark_prompt: str) -> None:
    """v0.13.0 — bug-report phrase detected. Find the most recent
    non-conversational log entry and copy it into candidates.jsonl for
    later review via /prompt-coach-beta:report-issue."""
    log = local_dir / "log.md"
    if not log.exists():
        return
    lines = [ln for ln in log.read_text(encoding="utf-8").splitlines()
             if ln.startswith("- [")]
    # Walk backwards to find the last substantive (non-conversational,
    # non-bug-report) entry.
    target_line: str | None = None
    for line in reversed(lines):
        m = re.search(r"outcome=(\S+)", line)
        if not m:
            continue
        outcome = m.group(1)
        if outcome in ("skipped:conversational",):
            continue
        # Also skip the entry for the bug-report phrase itself.
        pm = re.search(r"prompt=«([^»]*)»", line)
        if pm and is_bug_report_phrase(pm.group(1)):
            continue
        target_line = line
        break
    if not target_line:
        return
    candidates = local_dir / "candidates.jsonl"
    entry = {
        "flagged_at": _now_iso(),
        "mark_phrase_first_5_words": " ".join(mark_prompt.split()[:5]),
        "target_log_line": target_line,
    }
    with candidates.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def append_log(local_dir: Path, entry: dict) -> None:
    log = local_dir / "log.md"
    log.parent.mkdir(parents=True, exist_ok=True)
    date = _today()
    lines_out = []
    if not log.exists():
        lines_out.append("# prompt-coach log\n")
    header = f"## {date}\n"
    body = log.read_text(encoding="utf-8") if log.exists() else ""
    if header.strip() not in body:
        lines_out.append(header)
    fired = ", ".join(entry.get("fired", [])) or "—"
    chosen = entry.get("chosen") or "—"
    positives = ", ".join(entry.get("positive_fires", []) or []) or "—"
    mastery = ", ".join(entry.get("mastery_events", []) or []) or ""
    praise = entry.get("praise") or "—"
    corrections = ", ".join(entry.get("corrections", []) or [])
    outcome = entry.get("outcome", "?")
    prompt_preview = entry.get("prompt", "").replace("\n", " ")[:120]
    lines_out.append(
        f"- [{entry['t']}] fired=[{fired}] chosen={chosen} "
        f"positives=[{positives}] "
        + (f"mastered=[{mastery}] " if mastery else "")
        + (f"corrected=[{corrections}] " if corrections else "")
        + f"praise={praise} outcome={outcome} "
        f"prompt=«{prompt_preview}»"
    )
    with log.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines_out) + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        # Bad hook input; don't block the user's prompt.
        return 0

    prompt_raw = payload.get("prompt") or ""
    cwd = Path(payload.get("cwd") or os.getcwd())

    cfg = resolve_config(cwd)
    if cfg.get("nudge_style") not in ("both", "silent", "log-only", "inline"):
        cfg["nudge_style"] = "both"

    g = load_json(GLOBAL_STATE, blank_global_state())
    # Repair state schemas across upgrades.
    g.setdefault("normalization_stats", {
        "prompts_with_corrections": 0,
        "tokens_corrected_total": 0,
        "top_corrections": {},
    })
    g.setdefault("llm_fallback_stats", {
        "calls_total": 0, "fired_rules_via_fallback": 0,
    })

    local_dir = cwd / ".claude" / "prompt-coach"
    l = load_json(local_dir / "state.json", blank_local_state())

    # Increment prompt counters.
    g["prompt_count"] = int(g.get("prompt_count", 0)) + 1
    l["prompt_count"] = int(l.get("prompt_count", 0)) + 1

    # v0.13.0 — bug-report phrase: user flagged the PREVIOUS prompt's
    # analysis for review. Append the last non-conversational log entry
    # (which is the analysis being complained about) to candidates.jsonl.
    if is_bug_report_phrase(prompt_raw):
        _flag_previous_for_review(local_dir, prompt_raw)

    # Conversational short-circuit — "sure", "publish", "1 and 2", "go for
    # it" etc. are fragments answering an implicit question, not full
    # prompts. Coaching rules misfire on them and the typo normalizer
    # produces false corrections ("publish" → "polish"). Skip analysis
    # entirely but log so the user can audit what was skipped.
    if is_conversational(prompt_raw):
        g["updated_at"] = _now_iso()
        l["updated_at"] = _now_iso()
        save_json(GLOBAL_STATE, g)
        save_json(local_dir / "state.json", l)
        append_log(local_dir, {
            "t": _now_iso(),
            "fired": [],
            "positive_fires": [],
            "mastery_events": [],
            "chosen": None,
            "praise": None,
            "outcome": "skipped:conversational",
            "prompt": prompt_raw[:400],
            "corrections": [],
        })
        return 0

    # Typo normalization pass — makes the coach friendly to dyslexic
    # spellings without changing the rule catalog. Rules see the normalized
    # prompt; the original is preserved for the log.
    tolerance = int(cfg.get("typo_tolerance", 2))
    prompt, corrections = normalize_prompt(prompt_raw, tolerance)
    if corrections:
        ns = g["normalization_stats"]
        ns["prompts_with_corrections"] = int(ns.get("prompts_with_corrections", 0)) + 1
        ns["tokens_corrected_total"] = int(ns.get("tokens_corrected_total", 0)) + len(corrections)
        top = ns.setdefault("top_corrections", {})
        for orig, _fixed in corrections:
            k = orig.lower()
            top[k] = int(top.get(k, 0)) + 1

    # v0.9.0 — split practicing (capped at max_active) from mastered
    # (uncapped, evaluated on every prompt, longer cooldown).
    active_practicing, active_mastered = active_rules_split(cfg, g, l)
    active = active_practicing + active_mastered
    fired_practicing = [rid for rid in active_practicing if fires(prompt, rid)]
    fired_mastered = [rid for rid in active_mastered if fires(prompt, rid)]
    fired = fired_practicing + fired_mastered  # for logging + bookkeeping
    chosen = pick_nudge(fired_practicing, l, cfg, mastered=False)
    chosen_mastered: str | None = None
    if chosen is None and fired_mastered:
        chosen_mastered = pick_nudge(fired_mastered, l, cfg, mastered=True)

    threshold = int(cfg.get("graduation_threshold", 15))
    mastery_events: list[str] = []  # rule ids that graduated this prompt
    demoted_events: list[str] = []  # rule ids that lost mastery this prompt

    # Bookkeeping: update every active rule's streak.
    for rid in active:
        gr = g["rules"].setdefault(rid, {
            "status": "practicing",
            "fires_total": 0,
            "clean_streak": 0,
            "last_fired_at": None,
            "last_nudged_at": None,
            "graduated_at": None,
        })
        lr = l["rules"].setdefault(rid, {
            "fires_here": 0,
            "clean_streak_here": 0,
            "last_fired_at": None,
            "last_nudged_at": None,
            "last_nudged_prompt": None,
        })
        gr["status"] = gr.get("status") or "practicing"
        if rid in fired:
            gr["fires_total"] = int(gr.get("fires_total", 0)) + 1
            gr["clean_streak"] = 0
            gr["last_fired_at"] = _now_iso()
            lr["fires_here"] = int(lr.get("fires_here", 0)) + 1
            lr["clean_streak_here"] = 0
            lr["last_fired_at"] = _now_iso()
        else:
            gr["clean_streak"] = int(gr.get("clean_streak", 0)) + 1
            lr["clean_streak_here"] = int(lr.get("clean_streak_here", 0)) + 1

        # Graduate if we cleared the bar and the rule wasn't just fired.
        if (rid not in fired
            and gr["clean_streak"] >= threshold
            and gr.get("status") != "mastered"):
            gr["status"] = "mastered"
            gr["graduated_at"] = _now_iso()
            gr["post_mastery_fires"] = 0
            gr["post_mastery_fire_prompts"] = []
            mastery_events.append(rid)

        # v0.9.0 — post-mastery fire tracking (for optional auto-demotion).
        # Even if demotion is off, we track the counter so /stats can surface
        # regressions.
        if rid in fired and gr.get("status") == "mastered":
            gr["post_mastery_fires"] = int(gr.get("post_mastery_fires", 0)) + 1
            fire_prompts = list(gr.get("post_mastery_fire_prompts", []))
            fire_prompts.append(g["prompt_count"])
            demote_cfg = cfg.get("demote_on_regression") or {}
            window = int(demote_cfg.get("window", 30))
            fire_prompts = [p for p in fire_prompts if g["prompt_count"] - p <= window]
            gr["post_mastery_fire_prompts"] = fire_prompts

            if (demote_cfg.get("enabled", False)
                and len(fire_prompts) >= int(demote_cfg.get("threshold", 3))):
                gr["status"] = "practicing"
                gr["clean_streak"] = 0
                gr["demoted_at"] = _now_iso()
                gr["post_mastery_fires"] = 0
                gr["post_mastery_fire_prompts"] = []
                demoted_events.append(rid)

    outcome = "no-emit"
    context_line: str | None = None

    if chosen is not None:
        rule = RULES_BY_ID[chosen]
        gr = g["rules"][chosen]
        lr = l["rules"][chosen]
        gr["last_nudged_at"] = _now_iso()
        lr["last_nudged_at"] = _now_iso()
        lr["last_nudged_prompt"] = l["prompt_count"]
        l["last_nudge_prompt"] = l["prompt_count"]
        outcome = f"nudged:{cfg['nudge_style']}"

        mode = cfg["nudge_style"]
        # If we've paused, do not emit — but still record fire above.
        paused_until = int(cfg.get("pause_until_prompt", 0))
        if g["prompt_count"] <= paused_until:
            outcome = "paused"
        else:
            if mode == "both":
                streak = int(g["rules"][chosen].get("clean_streak", 0))
                print(_box(rule, streak, threshold, mode), file=sys.stderr, flush=True)
            if mode == "inline":
                streak = int(g["rules"][chosen].get("clean_streak", 0))
                context_line = _inline_context_for_claude(rule, streak, threshold)
            elif mode in ("both", "silent"):
                context_line = _context_for_claude(rule)
    elif chosen_mastered is not None:
        # v0.9.0 — mastered rule fires: soft refresher, longer cooldown.
        rule = RULES_BY_ID[chosen_mastered]
        gr = g["rules"][chosen_mastered]
        lr = l["rules"][chosen_mastered]
        gr["last_nudged_at"] = _now_iso()
        lr["last_nudged_at"] = _now_iso()
        lr["last_nudged_prompt"] = l["prompt_count"]
        l["last_nudge_prompt"] = l["prompt_count"]
        outcome = f"refresher:{cfg['nudge_style']}"

        mode = cfg["nudge_style"]
        paused_until = int(cfg.get("pause_until_prompt", 0))
        if g["prompt_count"] <= paused_until:
            outcome = "paused"
        else:
            # Days since graduation, if available.
            grad = gr.get("graduated_at")
            days_since = None
            if grad:
                try:
                    grad_dt = datetime.strptime(grad, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                    now_dt = datetime.now(timezone.utc)
                    days_since = max(0, (now_dt - grad_dt).days)
                except (ValueError, TypeError):
                    pass
            if mode == "both":
                print(_refresher_box(rule, days_since, mode),
                      file=sys.stderr, flush=True)
            if mode == "inline":
                context_line = _inline_context_for_claude_refresher(rule, days_since)
            elif mode in ("both", "silent"):
                context_line = (
                    f"[prompt-coach · refresher] Mastered rule '{rule.id}' "
                    f"({rule.name}) matched this prompt — light re-fire. "
                    f"Guidance: {rule.guidance} Continue with the task; no need "
                    f"to belabor the point unless the pattern keeps repeating."
                )

    # ---------------- Encouragement layer ---------------- #
    # Only consider praise on prompts that did NOT emit a nudge (Kohn 1993:
    # never dilute a correction with praise on the same prompt). Also skip
    # entirely if paused.
    positive_fires: list[str] = []
    praise_choice = None
    # v0.9.0 — refreshers count as "spoke this prompt" for Kohn's
    # don't-dilute-praise principle. If we said anything (nudge OR
    # refresher), no praise on the same prompt.
    nudged_this_prompt = ((chosen is not None or chosen_mastered is not None)
                          and outcome != "paused")
    paused_until = int(cfg.get("pause_until_prompt", 0))
    is_paused = g["prompt_count"] <= paused_until

    if not nudged_this_prompt and not is_paused:
        # Only run positives whose mirror rule is currently active (else the
        # user hasn't "graduated" out of noise on that concept yet, and the
        # positive would fire spuriously). For milestone events (mastery,
        # first-after-fire) we allow all positives since those are triggered
        # by state, not by the positive's own activation.
        for pid, p in POSITIVES_BY_ID.items():
            if p.mirrors in active or p.mirrors in (l.get("last_prompt_fired_rules") or []):
                try:
                    if p.check(prompt):
                        positive_fires.append(pid)
                except Exception:
                    pass  # never let a bad regex break the hook

        praise_choice = pick_praise(
            positive_fires, mastery_events, l, g, cfg, nudged_this_prompt)

    if praise_choice is not None:
        kind, pid_or_rid, praise_text, sources = praise_choice
        mode = cfg["nudge_style"]

        if kind == "mastery":
            header = f"Rule mastered: {RULES_BY_ID[pid_or_rid].name}"
        elif kind == "first-after-fire":
            p = POSITIVES_BY_ID[pid_or_rid]
            header = f"First-after-fire: {p.id} → mirror {p.mirrors}"
        else:
            p = POSITIVES_BY_ID[pid_or_rid]
            header = f"{p.id}"

        outcome = f"praised:{kind}:{cfg['nudge_style']}"
        if mode == "both":
            print(_praise_box(kind, header, praise_text, sources, mode),
                  file=sys.stderr, flush=True)
        if mode in ("both", "silent"):
            context_line = _praise_context(kind, pid_or_rid, praise_text)

        # State updates for praise
        g["praise_count"] = int(g.get("praise_count", 0)) + 1
        l["clean_prompts_since_praise"] = 0
        l["last_praise_at"] = _now_iso()
    else:
        # Increment clean-streak-since-praise only on prompts we didn't nudge
        # (nudge already implies noisy).
        if not nudged_this_prompt:
            l["clean_prompts_since_praise"] = int(
                l.get("clean_prompts_since_praise", 0)) + 1

    # Remember which rules fired THIS prompt so next prompt's "first-after-fire"
    # praise can trigger.
    l["last_prompt_fired_rules"] = list(fired)

    # Persist state.
    g["updated_at"] = _now_iso()
    l["updated_at"] = _now_iso()
    save_json(GLOBAL_STATE, g)
    save_json(local_dir / "state.json", l)

    # Log.
    append_log(local_dir, {
        "t": _now_iso(),
        "fired": fired,
        "positive_fires": positive_fires,
        "mastery_events": mastery_events,
        "demoted_events": demoted_events,
        "chosen": chosen or chosen_mastered,
        "praise": praise_choice[0] + ":" + praise_choice[1] if praise_choice else None,
        "outcome": outcome,
        "prompt": prompt_raw[:400],
        "corrections": [f"{o}→{c}" for o, c in corrections],
    })

    # Emit hook JSON if we have context for Claude.
    if context_line:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": context_line,
            }
        }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 — hook must never block
        print(f"prompt-coach: internal error suppressed: {exc}",
              file=sys.stderr)
        sys.exit(0)
