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
from datetime import datetime, timedelta, timezone
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
    # v0.29.0 — rendering simplified. The coach always renders inline
    # (as the opening block of Claude's response). The pre-v0.29
    # `nudge_style` config (both/silent/log-only/inline) is silently
    # ignored — inline is the only rendering that actually works in
    # a Claude Code CLI environment. Use `enabled: false` to silence
    # the coach entirely for this scope; `pause_until_prompt` still
    # works for temporary silence.
    "enabled": True,
    # v0.35.0 — liveness. On a clean prompt (nothing else fired), emit a
    # compact ambient one-liner confirming the coach ran + showing mastery
    # progress. Informational, not praise; distinct ✓ glyph. `ack_ratio`
    # rate-limits it: 1 = every clean prompt (heartbeat), higher = every
    # Nth. Set ack_clean=false to go back to silent-on-clean.
    "ack_clean": True,
    "ack_ratio": 1,
    # v0.36.0 — show full clickable doc URLs in the coach's Sources line
    # (collaborator block). On by default; terminals auto-linkify a bare
    # https URL so the user can Cmd/Ctrl-click to open the doc. Set false
    # for just the short anchor slug (e.g. "be-clear-and-direct").
    "show_source_urls": True,
    "graduation_threshold": 15,   # clean prompts in a row (recency/decay)
    # v0.27.0 — LEGACY evidence gate. Superseded by demonstration-driven
    # mastery in v0.40.0 (see `min_demonstrations`); retained for
    # forward-compat and ignored by the new graduation path.
    "min_fires_for_mastery": 1,
    # v0.40.0 — EARNED MASTERY. Mastery is driven by *demonstrations* — the
    # number of times a rule's mirroring positive detector fired (i.e. the
    # user actively USED the good technique), not by the mere absence of the
    # mistake. This fixes the flaw where rules graduated on clean prompts
    # that never exercised them.
    #   min_demonstrations — positive demonstrations required to master
    #   regression_guard   — clean prompts since the last fire required
    #                        alongside the demonstrations (no active relapse)
    #   inactive_after     — clean_streak with ZERO demonstrations after which
    #                        a rule retires `inactive` ("N/A to how you work")
    #                        instead of lingering; defaults to
    #                        graduation_threshold.
    "min_demonstrations": 3,
    "regression_guard": 3,
    "inactive_after": 15,
    # v0.41.0 (Proposal 2) — precision-gated adaptive activation. A rule the
    # user consistently rejects (low acceptance) is demoted to `dormant` and
    # stops firing; a small deterministic explore slot re-surfaces one dormant
    # rule every `explore_period` prompts to refresh its estimate. Plus a
    # rolling-window fatigue cap on total visible rewrites.
    "precision_gating": True,
    "precision_floor": 0.15,          # demote below this acceptance rate
    "min_outcomes_for_gating": 4,     # need this many outcomes before gating
    "explore_period": 10,             # re-admit a dormant rule every N prompts
    "nudge_window": 20,               # rolling window (prompts) for the cap
    "max_nudges_per_window": 6,       # max visible rewrites per window (0=off)
    # v0.41.0 (Proposal 3) — decaying mastery. A mastered rule carries a
    # review clock on an expanding schedule (days of NON-USE); each natural
    # use resets+expands it. If it lapses, the rule decays to `watch` and must
    # be freshly re-demonstrated to re-graduate (spaced retrieval practice).
    "review_intervals_days": [30, 90, 180],
    # v0.28.0 — proactive tips (advanced-technique suggestions). Distinct
    # from rules (which fire on problems in the prompt). Tips fire on-topic
    # for a technique the user could try. Two firing modes:
    #   * matching: heuristic matches + cooldown clear + ratio hit
    #   * graduation-unlock: paired to a mastered rule; fires once when
    #     the rule graduates. Baked-in learning sequence.
    "tips_enabled": True,
    "tip_cooldown_prompts": 100,   # min prompts between two fires of the same tip
    "tip_ratio": 5,                # 1 in N matching opportunities fires (variable-ratio)
    "cooldown_prompts": 5,        # min prompts between same-rule nudges
    "max_active_rules": 6,        # never nag on more than this many rules at once
                                  # (v0.12.0: raised 5→6 to fit the new L1 tier
                                  # with no-answer-shape included)
    "pause_until_prompt": 0,      # user-set: skip nudging until global_prompt_count > this
    "disabled_rules": [],         # user can permanently silence a rule id
    # v0.38.0 — the v0.16 anti-habituation config (saturation_threshold,
    # silence_window, silence_duration, disclosure_medium_at,
    # disclosure_short_at) and v0.17 voice config (voice_preset,
    # voice_source) were removed with the legacy nudge emit path. Under
    # collaborator mode Claude writes each rewrite fresh, so there's no
    # repeated-text to habituate to and no preset to pick.
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
# CONFIG_SCHEMA — metadata for every DEFAULT_CONFIG key (v0.18+).
# ---------------------------------------------------------------------------
# Single source of truth used by scripts/config.py (the /prompt-coach-beta:config
# slash command) to render the dashboard, describe keys, and validate `set`.
# Adding a new config option in a future release means one entry here — the
# dashboard, describer, and validator pick it up automatically.
#
# Shape per key:
#   category:    which group in the dashboard
#   type:        "str" | "int" | "bool" | "list[str]" | "obj"
#   choices:     optional list of allowed values (for str with enumerable domain)
#   description: one-line human explanation
#   example:     a concrete example value (or None for obvious types)
#   since:       version string this key was introduced

CONFIG_SCHEMA = {
    # ── output ──
    "enabled": {
        "category": "output",
        "type": "bool",
        "description": "Master switch (v0.29+). When false, the coach's "
                       "UserPromptSubmit hook returns immediately without "
                       "analyzing, logging, or emitting. Use `pause_until_prompt` "
                       "for temporary silence; use `enabled=false` to fully "
                       "disable the coach for this scope. Rendering is always "
                       "inline as of v0.29 — the pre-v0.29 nudge_style options "
                       "(both/silent/log-only) are silently ignored.",
        "example": True,
        "since": "0.29.0",
    },
    "ack_clean": {
        "category": "output",
        "type": "bool",
        "description": "Emit a compact ambient one-liner on a clean prompt "
                       "(nothing else fired) confirming the coach ran + showing "
                       "the active rule closest to mastery. A liveness heartbeat, "
                       "not praise — distinct ✓ glyph, informational not "
                       "evaluative. On by default; set false to go silent on "
                       "clean prompts.",
        "example": True,
        "since": "0.35.0",
    },
    "ack_ratio": {
        "category": "output",
        "type": "int",
        "description": "Rate-limit for ack_clean: emit the liveness line every "
                       "Nth clean prompt. 1 = every clean prompt (default; a "
                       "steady heartbeat). Raise to 5/10 for a quieter pulse.",
        "example": 1,
        "since": "0.35.0",
    },
    "show_source_urls": {
        "category": "output",
        "type": "bool",
        "description": "Show full clickable doc URLs in the coach's Sources "
                       "line (the collaborator block), so you can Cmd/Ctrl-click "
                       "to open the Anthropic guide section. On by default. Set "
                       "false to show just the short anchor slug (e.g. "
                       "'be-clear-and-direct') and keep the block compact.",
        "example": True,
        "since": "0.36.0",
    },
    "pause_until_prompt": {
        "category": "output",
        "type": "int",
        "description": "Skip all nudging until global prompt_count exceeds this number. "
                       "Use to silence the coach for N prompts (say 'coach pause N').",
        "example": None,
        "since": "0.5.0",
    },
    # ── rule-activation ──
    "max_active_rules": {
        "category": "rule-activation",
        "type": "int",
        "description": "Cap on practicing rules active at once. As lower-tier rules "
                       "master, higher-tier ones activate up to this cap.",
        "example": 6,
        "since": "0.5.0",
    },
    "disabled_rules": {
        "category": "rule-activation",
        "type": "list[str]",
        "description": "Rule ids to permanently silence. Say 'coach off <rule-id>' to "
                       "append or 'coach on <rule-id>' to remove.",
        "example": ["no-few-shot"],
        "since": "0.5.0",
    },
    "graduation_threshold": {
        "category": "rule-activation",
        "type": "int",
        "description": "Clean prompts in a row a rule tracks as a recency/decay "
                       "signal. Since v0.40 this no longer drives mastery (see "
                       "min_demonstrations); it feeds the regression guard and the "
                       "inactive-after default.",
        "example": 15,
        "since": "0.5.0",
    },
    "min_fires_for_mastery": {
        "category": "rule-activation",
        "type": "int",
        "description": "LEGACY (v0.27) evidence gate, superseded by "
                       "min_demonstrations in v0.40. Retained for forward-compat; "
                       "ignored by the demonstration-driven graduation path.",
        "example": 1,
        "since": "0.27.0",
    },
    "min_demonstrations": {
        "category": "rule-activation",
        "type": "int",
        "description": "EARNED MASTERY (v0.40+). Number of times a rule's mirroring "
                       "positive detector must fire — i.e. times you actively USED the "
                       "good technique — before the rule can master. Absence of the "
                       "mistake no longer counts; demonstration does.",
        "example": 3,
        "since": "0.40.0",
    },
    "regression_guard": {
        "category": "rule-activation",
        "type": "int",
        "description": "Clean prompts since the last fire required alongside the "
                       "demonstrations for mastery (v0.40+) — proves no active relapse "
                       "at the moment of graduation.",
        "example": 3,
        "since": "0.40.0",
    },
    "inactive_after": {
        "category": "rule-activation",
        "type": "int",
        "description": "Clean_streak with ZERO demonstrations after which a rule "
                       "retires `inactive` ('N/A to how you work') instead of "
                       "lingering as practicing (v0.40+). Defaults to "
                       "graduation_threshold.",
        "example": 15,
        "since": "0.40.0",
    },
    "precision_gating": {
        "category": "rule-activation",
        "type": "bool",
        "description": "ADAPTIVE ACTIVATION (v0.41+). When on, a rule whose "
                       "acceptance rate (accepted+edited)/outcomes falls below "
                       "precision_floor is demoted to `dormant` and stops firing; "
                       "an explore slot periodically re-surfaces it.",
        "example": True,
        "since": "0.41.0",
    },
    "precision_floor": {
        "category": "rule-activation",
        "type": "float",
        "description": "Acceptance-rate floor (v0.41+): a rule below this over "
                       "min_outcomes_for_gating recorded outcomes is demoted "
                       "dormant. Default 0.15 (only rules rejected ~85%+ of the "
                       "time).",
        "example": 0.15,
        "since": "0.41.0",
    },
    "min_outcomes_for_gating": {
        "category": "rule-activation",
        "type": "int",
        "description": "How many recorded accept/edit/reject outcomes a rule needs "
                       "before the precision gate applies to it (v0.41+).",
        "example": 4,
        "since": "0.41.0",
    },
    "explore_period": {
        "category": "rule-activation",
        "type": "int",
        "description": "Explore/exploit (v0.41+): re-admit one dormant rule every N "
                       "prompts to refresh its acceptance estimate so a rule noisy "
                       "in only one context isn't buried forever. 0 disables.",
        "example": 10,
        "since": "0.41.0",
    },
    "nudge_window": {
        "category": "output",
        "type": "int",
        "description": "Rolling window (in prompts) for the fatigue cap (v0.41+).",
        "example": 20,
        "since": "0.41.0",
    },
    "max_nudges_per_window": {
        "category": "output",
        "type": "int",
        "description": "FATIGUE CAP (v0.41+): max visible rewrites within "
                       "nudge_window prompts; over the cap, fires are still logged "
                       "and bookkept but the rewrite isn't rendered. 0 disables.",
        "example": 6,
        "since": "0.41.0",
    },
    "review_intervals_days": {
        "category": "rule-activation",
        "type": "list",
        "description": "DECAYING MASTERY (v0.41+): expanding review schedule in days "
                       "of NON-USE. A mastered rule unused past the current interval "
                       "decays to `watch` and must be re-demonstrated; each natural "
                       "use resets + advances to the next interval.",
        "example": [30, 90, 180],
        "since": "0.41.0",
    },
    "tips_enabled": {
        "category": "output",
        "type": "bool",
        "description": "Enable proactive tips (v0.28+): 💡 suggestions pointing at "
                       "advanced techniques you could try. Distinct from rules which "
                       "fire on prompt problems — tips fire on-topic for techniques "
                       "you haven't used. Fires on matching prompts (rate-limited) "
                       "and on rule masteries (paired scaffolding).",
        "example": True,
        "since": "0.28.0",
    },
    "tip_cooldown_prompts": {
        "category": "output",
        "type": "int",
        "description": "Minimum prompts between two fires of the same tip (v0.28+). "
                       "Anti-nagging cap; the coach shouldn't remind you about the "
                       "same technique every few prompts.",
        "example": 100,
        "since": "0.28.0",
    },
    "tip_ratio": {
        "category": "output",
        "type": "int",
        "description": "Variable-ratio: 1 in N matching + cooldown-clear opportunities "
                       "actually fires a tip (v0.28+). Lower = more frequent tips.",
        "example": 5,
        "since": "0.28.0",
    },
    "cooldown_prompts": {
        "category": "rule-activation",
        "type": "int",
        "description": "Minimum prompts between two fires of the same practicing rule "
                       "(anti-nagging cap).",
        "example": 5,
        "since": "0.5.0",
    },
    # ── mastery ──
    "mastered_cooldown_prompts": {
        "category": "mastery",
        "type": "int",
        "description": "Cooldown between refresher fires on mastered rules. 10x the "
                       "practicing cooldown by default. Set to 0 to disable refresher "
                       "firing (permanent silence on mastered rules).",
        "example": 50,
        "since": "0.9.0",
    },
    "demote_on_regression": {
        "category": "mastery",
        "type": "obj",
        "description": "Auto-demote a mastered rule that fires threshold+ times within "
                       "window prompts. Shape: {enabled, threshold, window}. Off by "
                       "default — surprise reactivation feels punitive.",
        "example": {"enabled": True, "threshold": 3, "window": 30},
        "since": "0.9.0",
    },
    # ── praise ──
    "praise_ratio": {
        "category": "praise",
        "type": "int",
        "description": "1 praise per N clean prompts with a positive fire (variable-"
                       "ratio, Kohn's don't-dilute threshold). Lower = more frequent.",
        "example": 10,
        "since": "0.3.0",
    },
    "praise_on_mastery": {
        "category": "praise",
        "type": "bool",
        "description": "Celebrate whenever a rule graduates to mastered.",
        "example": True,
        "since": "0.3.0",
    },
    "praise_on_first_after_fire": {
        "category": "praise",
        "type": "bool",
        "description": "Celebrate when you correct the exact thing you were nudged on "
                       "in the previous prompt.",
        "example": True,
        "since": "0.3.0",
    },
    "disable_praise": {
        "category": "praise",
        "type": "bool",
        "description": "Silence all praise but keep nudges. Praise+correction on the "
                       "same prompt would dilute both (Kohn).",
        "example": False,
        "since": "0.3.0",
    },
    "praise_novelty_window": {
        "category": "praise",
        "type": "int",
        "description": "Don't repeat the same praise phrasing within N praises.",
        "example": 5,
        "since": "0.16.0",
    },
    # ── typo-tolerance ──
    "typo_tolerance": {
        "category": "typo-tolerance",
        "type": "int",
        "description": "Levenshtein distance for typo normalization (0 disables). "
                       "Adaptive: distance-1 for short tokens (≤6 chars), distance-2 "
                       "for longer.",
        "example": 2,
        "since": "0.5.0",
    },
    # ── llm-fallback (stub) ──
    "llm_fallback": {
        "category": "llm-fallback",
        "type": "obj",
        "description": "Opt-in stub. If enabled AND no rule fired via regex AND the "
                       "prompt is long, an optional model call would classify against "
                       "the rule catalog. Deferred until real-use data justifies it.",
        "example": {"enabled": True, "model": "haiku", "min_words": 20},
        "since": "0.6.0",
    },
}


def config_key_source(key: str, global_cfg: dict, repo_cfg: dict) -> str:
    """v0.18.0 — where did the resolved value come from? Used by /config show."""
    if key in repo_cfg:
        return "repo"
    if key in global_cfg:
        return "global"
    return "default"


def config_categories() -> list[str]:
    """v0.18.0 — canonical category order for the dashboard."""
    seen = []
    for entry in CONFIG_SCHEMA.values():
        c = entry["category"]
        if c not in seen:
            seen.append(c)
    return seen


def config_keys_in_category(category: str) -> list[str]:
    """v0.18.0 — every key that lives in the named category."""
    return [k for k, v in CONFIG_SCHEMA.items() if v["category"] == category]


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
    coaching rules would misfire (e.g. 'sure', '1 and 2 yes 3', dyslexic variants).
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


# ── v0.24.0 — transcript-aware picker-answer detection ─────────────────────
# When Claude's previous turn asked a multiple-choice question (via
# AskUserQuestion) or was drafted-for-you continuation, the user's next
# prompt is really a picker answer, not their fresh authored ask — so any
# rule the answer text happens to match is a false positive. Reading the
# session transcript catches this deterministically for AskUserQuestion and
# heuristically for prefilled option-list continuations.

_CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"

# Only tail the last N lines of the transcript — the last assistant turn
# is always in the very recent tail, and transcripts can be 15+ MB.
_TRANSCRIPT_TAIL_LINES = 80

# v0.34.1 — Heuristic marker for a prefilled option-list continuation.
# History: v0.24 accepted `[?:]` + <=2000 chars + >=2 list items *anywhere*
# in the assistant text. In practice this over-fired catastrophically —
# any structured prose with a `:` intro + bulleted items looked like a
# picker, so users' real prompts got skipped as "picker answers" for
# hours on end (Alex reported "no nudges since last release" 2026-07-05).
# Tightened three ways:
#   1. Require `?` (not `:`) — a question mark actually signals a
#      picker; colons appear in "Changes:", "Sections:", "Details:" prose
#      that is NOT a picker.
#   2. Tighter distance: `?` must be within 600 chars of the list start,
#      not 2000. Real pickers have the question close to the options.
#   3. Applied to the TAIL of the assistant text only (last 1500 chars).
#      A picker in the middle of a long response followed by unrelated
#      prose is not a picker interaction with the user's next prompt.
_OPTION_LIST_RE = re.compile(
    r"(?:"
    # Form A: "Which? A/B/C" — question then list
    r"\?[^?]{0,600}?"
    r"(?:^\s*(?:[-*•]|\d+\.|\(?[a-eA-E][.\)])\s+.+(?:\n|$)){2,}"
    r"|"
    # Form B: "A/B/C. Which?" — list then question within 600 chars
    r"(?:^\s*(?:[-*•]|\d+\.|\(?[a-eA-E][.\)])\s+.+\n){2,}[^?]{0,600}?\?"
    r")",
    re.MULTILINE,
)


def _current_transcript_path(cwd: Path) -> Path | None:
    """Return the most-recently-modified transcript file for the cwd's
    session directory, or None. The directory-naming convention is a
    slash-to-dash slug of the absolute cwd. Handles missing directories
    gracefully so a stale/broken lookup can never block a user prompt."""
    try:
        slug = str(cwd.resolve()).replace("/", "-")
        d = _CLAUDE_PROJECTS_DIR / slug
        if not d.exists():
            return None
        transcripts = list(d.glob("*.jsonl"))
        if not transcripts:
            return None
        return max(transcripts, key=lambda p: p.stat().st_mtime)
    except (OSError, ValueError):
        return None


def _tail_lines(path: Path, n: int) -> list[str]:
    """Read the last n lines of a file efficiently by seeking near EOF."""
    try:
        size = path.stat().st_size
        # For small files just read everything.
        if size < 128 * 1024:
            return path.read_text(errors="replace").splitlines()[-n:]
        # For large files, seek backwards in 8 KB chunks until we have n newlines.
        chunk = 8192
        offset = size
        buf = b""
        with path.open("rb") as f:
            while offset > 0 and buf.count(b"\n") < n + 1:
                read_size = min(chunk, offset)
                offset -= read_size
                f.seek(offset)
                buf = f.read(read_size) + buf
        text = buf.decode("utf-8", errors="replace")
        return text.splitlines()[-n:]
    except OSError:
        return []


def _last_assistant_turn(cwd: Path) -> dict | None:
    """Locate the most recent `type: assistant` entry in the current
    transcript. Returns the parsed JSON dict, or None if nothing found."""
    t = _current_transcript_path(cwd)
    if not t:
        return None
    for line in reversed(_tail_lines(t, _TRANSCRIPT_TAIL_LINES)):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") == "assistant":
            return entry
    return None


def _picker_reason(entry: dict) -> str | None:
    """Classify an assistant turn as a picker turn:
    'multi-choice-answer' → AskUserQuestion tool_use present (definitive)
    'option-list-answer'  → text ends with `?` followed by a bulleted/
                            numbered list (heuristic; catches prefilled
                            continuations that the model drafts inline)
    None                  → not a picker turn
    """
    content = entry.get("message", {}).get("content", [])
    if not isinstance(content, list):
        return None
    text_chunks: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if (block.get("type") == "tool_use"
                and block.get("name") == "AskUserQuestion"):
            return "multi-choice-answer"
        if block.get("type") == "text":
            t = block.get("text", "")
            if isinstance(t, str):
                text_chunks.append(t)
    text = "\n".join(text_chunks)
    # v0.34.1 — check only the tail of the assistant text. A picker in the
    # middle of a long response followed by hundreds of chars of unrelated
    # prose isn't a picker interaction; the user's next prompt is a fresh
    # ask, not a picker answer.
    if text and _OPTION_LIST_RE.search(text[-1500:]):
        return "option-list-answer"
    return None


def picker_answer_reason(cwd: Path) -> str | None:
    """Public entry point: check the most-recent assistant turn in the
    current transcript. Returns a picker-reason string ('multi-choice-answer'
    / 'option-list-answer') if the last turn was a picker turn, else None.
    Never raises — a missing/broken transcript resolves to None so the
    coach continues to analyze prompts normally."""
    try:
        entry = _last_assistant_turn(cwd)
    except Exception:
        return None
    if not entry:
        return None
    try:
        return _picker_reason(entry)
    except Exception:
        return None


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
    guidance: str                 # short hint for Claude's additionalContext
    sources: list[tuple[str, str]]  # (title, url)
    check: Callable[[str], bool]
    # v0.20.0 — canonical Anthropic prompt-engineering guide section this rule
    # traces to. None = no upstream mapping (Claude-Code-specific rules like
    # no-skill-lookup have no Anthropic-guide equivalent). Format: section
    # slug from platform.claude.com/docs/en/build-with-claude/prompt-engineering/
    # claude-prompting-best-practices — used by /prompt-coach-beta:config
    # sources <rule-id> to surface a traceable citation.
    anthropic_ref: str | None = None


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
    # v0.15.0 — evidence: "Run a brainstorm panel on ..." + "review other
    # prompts and find issues" both fired nothing (run/review not verbs).
    "run", "review",
)

# Hedge prefixes — real English people prepend to action asks. Strip them
# so "try to deploy" is analyzed as "deploy". v0.11.0.
# v0.15.0 additions — evidence: "i think X", "now create Y", "let me Z" all
# fired nothing in the log because the analyzer couldn't see the action.
_HEDGE_PREFIXES = re.compile(
    r"^(try to|try and|let'?s|going to|gonna|need to|"
    r"want to|wanna|should|could|would|might|"
    r"please|can you|could you|would you|"
    # v0.15.0 — opinion / continuation hedges
    r"i think|i feel|i want to|let me|now|actually|basically|so)\s+"
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
    # v0.15.0 — dropped standalone "check " from DoD markers. Evidence:
    # "commit and check infra for creds" was falsely satisfied because
    # "check " appeared in the string, but "check infra" is investigative
    # not verification. Specific check-DoD patterns handled below.
    dod_markers = (
        "until ", "verify", "test", "ensure", " so that ", "passes",
        "green", " ci ", "expect", "assert", "output should", "should return",
        "should match", "coverage", "no error", "no warning", "definition of done",
        "acceptance",
    )
    if any(m in pl for m in dod_markers):
        return False
    # v0.15.0 — specific check-DoD patterns (check X works/passes/etc.)
    if re.search(
        r"\bcheck\s+(that|it|this|the\s+\w+)\s*[^.]*"
        r"\b(work|pass|green|build|ci\b|succeed|complete)",
        pl,
    ):
        return False
    return True


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
    r"""Information-seeking question with no format spec — evidence: real
    prompts like 'what are lsp servers', 'how much of github app support
    do we have?', 'Do we have enough for release?', and 'Are there java
    libs...' were firing nothing at all.

    v0.12.0: elevated from L2 → L1 (fundamentals) and broadened q regex
    to include 'do we / does it / can we / should we / are there' forms.

    v0.15.0: (reverted mid-sentence relaxation — over-fired on statements
    containing 'how do we / how do i' phrases in normal English. Kept
    strict `^\s*` anchor. Edge case '503 should be done can you check'
    accepted as a miss; it's ambiguous.)"""
    # First sentence only, so trailing sentences don't affect the check.
    first_sentence = re.split(r"[.!?\n]", prompt, maxsplit=1)[0]
    pl = first_sentence.lower()
    q = re.search(
        r"^\s*(what (are|is|kinds|types|options)|"
        r"how (much|many|do|does|can|should|would)|"
        r"which \w+ (should|are|is|would)|why (should|is|are|does|doesn.?t)|"
        r"does (\w+ )?exist|is there|are there|"
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
    # v0.15.0 — evidence: "review other prompts and find issues" and
    # "review alol new promts and confirm ..." both fired nothing.
    # Broadened to include: review (other|these|previous|N|all|latest|recent|new).
    critique = re.search(
        r"\b(review (this|my|the|results|findings|changes|code|output|design|plan|"
        r"other|these|previous|all|latest|recent|new|\d+)|"
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


def rule_incremental_routing(prompt: str) -> bool:
    """v0.39.0 — flag a multi-step task being routed one terse step at a time
    ('continue one after another', 'do the next one', 'keep going through
    them'). Each such step costs a human round-trip and re-establishes
    context; the remedy is to batch the sequence into a TaskCreate checklist
    (or a Workflow for a big fan-out) and let it run autonomously.

    Bare 'continue' / 'next' are caught by is_conversational() upstream and
    never reach here — this fires on the phrasings that carry an explicit
    'do these sequentially' intent while still routing per step. Vetoed when
    the user already names a batching mechanism (task list / plan / workflow /
    in parallel)."""
    pl = prompt.lower()
    seq = re.search(
        r"\b(one after another|one after the other|one at a time|"
        r"one by one|do the next one|the next one|do the rest|"
        r"keep going|go through (?:them|the list|these|all)|"
        r"continue through|through them all|do them (?:in )?sequen|"
        r"in sequence|sequentially|next task)\b", pl)
    if not seq:
        return False
    batched = re.search(
        r"\b(task ?list|to-?dos?|checklist|\bplan\b|workflow|taskcreate|"
        r"all at once|in parallel|at the same time|batch|numbered list)\b", pl)
    return not bool(batched)


# ---- v0.20.0 — new rules covering Anthropic-guide gaps ---------------------

def rule_no_xml_structure(prompt: str) -> bool:
    """v0.20.0 — flag prompts with substantial pasted content (code fence or
    ≥7-line indented block) that don't use XML-style tags to delimit it.
    Fires only when there's *both* significant pasted content AND no tags —
    short asks with a one-line snippet are unaffected."""
    # Indented-block content: 7+ consecutive lines starting with 4 spaces or tab
    lines = prompt.splitlines()
    max_indented_run = 0
    run = 0
    for line in lines:
        if line.startswith("    ") or line.startswith("\t"):
            run += 1
            max_indented_run = max(max_indented_run, run)
        else:
            run = 0
    # Code-fence content: 7+ lines between triple backticks
    fence_lines = 0
    in_fence = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            fence_lines += 1
    substantial_paste = max_indented_run >= 7 or fence_lines >= 7
    if not substantial_paste:
        return False
    # Any XML-style tag: <foo> </foo> <foo/> <foo attr="x">
    # We're liberal here — a single tag is enough to say "user is aware of the technique"
    has_tag = re.search(r"<[a-z][\w-]*(?:\s+[^>]*)?>", prompt, re.IGNORECASE)
    return not bool(has_tag)


def rule_no_classical_role(prompt: str) -> bool:
    """v0.20.0 — flag CRITIQUE / REVIEW / AUDIT / SECURITY asks that don't
    invoke a role. Distinct from `no-role-for-critique` (which nudges toward
    Claude Code's /roles:as); this is the classical prompt technique of 'You
    are a senior X' inline. Fires only on medium-long prompts (>15 words) so
    it doesn't catch quick asks."""
    words = prompt.split()
    if len(words) < 15:
        return False
    pl = prompt.lower()
    high_stakes = re.search(
        r"\b(review|audit|critique|evaluate|assess|analyze the|"
        r"security review|threat model|design review|architecture review|"
        r"code review)\b", pl)
    if not high_stakes:
        return False
    has_role = re.search(
        r"\byou are (?:a|an|the|acting)\b|"
        r"\bact as (?:a|an|the)\b|"
        r"\byour role is\b|"
        r"\bpretend (?:you'?re|you are)\b|"
        r"\bfrom the perspective of\b|"
        r"\bassume you'?re\b|"
        r"\btake the role of\b|"
        r"\b/roles?:as\b", pl)
    return not bool(has_role)


_OVERTHINKING_MARKERS = [
    r"\bmake sure (?:to|that|you)\b",
    r"\bbe (?:very |extra |especially )?careful\b",
    r"\bplease also\b",
    r"\bdon'?t forget (?:to )?\b",
    r"\bremember to\b",
    r"\balso (?:make sure|remember|note|ensure)\b",
    r"\bfurthermore\b",
    r"\bin addition,\b",
    r"\bit is (?:very |extremely |critical(?:ly)? )?important\b",
    r"\babsolutely (?:must|need|have to)\b",
    r"\bevery (?:single )?(?:file|line|method|function|case)\b",
    r"\bexhaustively\b",
    r"\bthoroughly\b.*\bthoroughly\b",
    r"\bplease ensure\b",
]


def rule_overthinking_warning(prompt: str) -> bool:
    """v0.20.0 — flag prompts stacked with elaboration/thoroughness markers
    that push Claude toward over-scoped, over-cautious work. Anthropic's guide
    explicitly warns about this. Conservative: fires only on ≥3 markers AND
    prompt ≥60 words (long enough to be over-elaborated; short careful prompts with a few caveats are legitimate)."""
    words = prompt.split()
    if len(words) < 60:
        return False
    pl = prompt.lower()
    hits = sum(1 for pat in _OVERTHINKING_MARKERS if re.search(pat, pl))
    return hits >= 3


def rule_test_goalseeking(prompt: str) -> bool:
    """v0.20.0 — flag prompts that ask for test-passing without correctness
    intent. Anthropic's guide has a whole section on this failure mode. Fires
    on 'make the tests pass' / 'fix the tests' / 'get CI green' without any
    correctness signal ('actually work', 'the bug', 'the real issue')."""
    pl = prompt.lower()
    goalseek = re.search(
        r"\b(make (?:the )?tests? (?:pass|green)|"
        r"get (?:the )?tests? (?:passing|green)|"
        r"fix (?:the )?(?:broken )?tests?\b|"
        r"(?:make|get) ci (?:green|pass|passing)|"
        r"just (?:need|want) (?:the )?(?:tests? |ci )?to pass)\b", pl)
    if not goalseek:
        return False
    correctness = re.search(
        r"\b(actually works?|actually correct|"
        r"real (?:bug|issue|cause)|"
        r"root cause|underlying|fix the bug|fix the issue|"
        r"not (?:just|only) (?:pass|green)|"
        r"correctness|verify (?:the|it) works?)\b", pl)
    return not bool(correctness)


def rule_no_verify_before_claim(prompt: str) -> bool:
    """v0.20.0 — flag asks that request an ASSERTION about code/state
    ('does X exist', 'is Y used', 'which files reference Z') without asking
    for the receipt (file:line, quoted source). Anthropic's hallucination
    guardrail for agentic coding. Distinct from `no-uncertainty-budget`
    (which is about admitting uncertainty); this is about demanding evidence
    BEFORE accepting the answer."""
    pl = prompt.lower()
    assertion_ask = re.search(
        r"\b(does (?:it|this|that|the [a-z]+) (?:exist|use|call|reference|handle|support)|"
        r"is (?:it|this|the [a-z]+) (?:used|called|referenced|handled|supported|imported)|"
        r"which (?:files?|modules?|packages?|functions?|methods?) (?:use|reference|import|call|touch)|"
        r"where (?:is|does) (?:the |this )?[a-z]+ (?:defined|used|called|handled)|"
        r"are there any (?:files?|places?|callers?|usages?))\b", pl)
    if not assertion_ask:
        return False
    receipt = re.search(
        r"\b(with (?:the )?(?:file|line|path|code|snippet)|"
        r"cite|show me the (?:code|line|file|path)|"
        r"file:line|line numbers?|"
        r"quote the|paste the|"
        r"prove it|proof|evidence|"
        r"before (?:saying|claiming|answering))\b", pl)
    return not bool(receipt)


def rule_no_edit_preference(prompt: str) -> bool:
    """v0.20.0 — flag 'create X' / 'write a new Y' prompts that don't state
    an edit-existing preference. Anthropic's 'Reduce file creation' section
    calls this out for agentic coding. Fires on create/write/make + new file
    types when there's no signal that the user prefers editing existing code."""
    pl = prompt.lower()
    creation_ask = re.search(
        r"\b(create|write|add|make)\s+(?:a\s+)?"
        r"(?:new\s+)?"
        r"(script|helper|utility|util|file|module|class|component|"
        r"function|method|package|library|program|tool|wrapper)\b", pl)
    if not creation_ask:
        return False
    edit_pref = re.search(
        r"\b(prefer(?:red)? (?:to )?(?:edit|update|extend|modify|reuse)|"
        r"only if (?:none|no|there'?s no)|"
        r"if (?:one )?(?:doesn'?t|does not) (?:already )?exist|"
        r"reuse existing|extend (?:the )?existing|"
        r"edit (?:the )?existing|update (?:the )?existing|"
        r"instead of creating|"
        r"unless there'?s (?:a|an|already))\b", pl)
    return not bool(edit_pref)


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

# v0.20.0 — Anthropic prompting-best-practices sections (fetched 2026-07-03,
# platform.claude.com is the current stable host; docs.anthropic.com still
# 301-redirects).
_ANTHROPIC_BEST = ("https://platform.claude.com/docs/en/build-with-claude/"
                   "prompt-engineering/claude-prompting-best-practices")
SRC_ANTHROPIC_XML = ("Anthropic — Structure prompts with XML tags",
                     f"{_ANTHROPIC_BEST}#structure-prompts-with-xml-tags")
SRC_ANTHROPIC_ROLE = ("Anthropic — Give Claude a role",
                      f"{_ANTHROPIC_BEST}#give-claude-a-role")
SRC_ANTHROPIC_OVERTHINK = ("Anthropic — Overthinking and excessive thoroughness",
                           f"{_ANTHROPIC_BEST}#overthinking-and-excessive-thoroughness")
SRC_ANTHROPIC_OVEREAGER = ("Anthropic — Overeagerness in agentic systems",
                           f"{_ANTHROPIC_BEST}#overeagerness")
SRC_ANTHROPIC_TESTGAME = ("Anthropic — Avoid focusing on passing tests and hard-coding",
                          f"{_ANTHROPIC_BEST}#avoid-focusing-on-passing-tests-and-hard-coding")
SRC_ANTHROPIC_HALLUCINATE = ("Anthropic — Minimizing hallucinations in agentic coding",
                             f"{_ANTHROPIC_BEST}#minimizing-hallucinations-in-agentic-coding")
SRC_ANTHROPIC_FILECREATE = ("Anthropic — Reduce file creation in agentic coding",
                            f"{_ANTHROPIC_BEST}#reduce-file-creation-in-agentic-coding")
SRC_ANTHROPIC_CONTEXT = ("Anthropic — Add context to improve performance",
                         f"{_ANTHROPIC_BEST}#add-context-to-improve-performance")
SRC_ANTHROPIC_FORMAT = ("Anthropic — Control the format of responses",
                        f"{_ANTHROPIC_BEST}#control-the-format-of-responses")
SRC_ANTHROPIC_VERBOSITY = ("Anthropic — Communication style and verbosity",
                           f"{_ANTHROPIC_BEST}#communication-style-and-verbosity")
SRC_ANTHROPIC_PARALLEL = ("Anthropic — Optimize parallel tool calling",
                          f"{_ANTHROPIC_BEST}#optimize-parallel-tool-calling")
SRC_ANTHROPIC_SUBAGENT = ("Anthropic — Subagent orchestration",
                          f"{_ANTHROPIC_BEST}#subagent-orchestration")
SRC_ANTHROPIC_AUTONOMY = ("Anthropic — Balancing autonomy and safety",
                          f"{_ANTHROPIC_BEST}#balancing-autonomy-and-safety")
SRC_ANTHROPIC_CHAINCOMPLEX = ("Anthropic — Chain complex prompts",
                              f"{_ANTHROPIC_BEST}#chain-complex-prompts")
SRC_LANGCHAIN_PLANEXEC = ("LangChain — Plan-and-execute agents",
                          "https://www.langchain.com/blog/planning-agents")

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
        guidance=(
            "User's prompt starts with an unresolved pronoun. If context makes the "
            "referent unambiguous, proceed; otherwise ask ONE short clarifying "
            "question before diving in."
        ),
        sources=[SRC_ANTHROPIC_BE_CLEAR, SRC_CC_BESTPRACTICE],
        check=rule_vague_reference,
        anthropic_ref="be-clear-and-direct",
    ),
    Rule(
        id="no-definition-of-done",
        tier=1,
        name="No definition of done",
        guidance=(
            "User's prompt is an action verb with no acceptance criteria. Before "
            "acting, restate your interpretation of 'done' in one sentence, and "
            "invite a correction if it's wrong."
        ),
        sources=[SRC_ANTHROPIC_BE_CLEAR, SRC_CC_BESTPRACTICE, SRC_SIMONW],
        check=rule_no_definition_of_done,
        anthropic_ref="be-clear-and-direct",
    ),
    Rule(
        id="unbounded-scope",
        tier=1,
        name="Unbounded scope",
        guidance=(
            "User's prompt has an unbounded scope word attached to a mutating "
            "verb. Ask them to constrain (path glob, module, or read-only) BEFORE "
            "doing multi-file edits."
        ),
        sources=[SRC_ANTHROPIC_OVERVIEW, SRC_CC_BESTPRACTICE],
        check=rule_unbounded_scope,
        anthropic_ref="be-clear-and-direct",
    ),
    Rule(
        id="improve-without-metric",
        tier=1,
        name="Improve without a metric",
        guidance=(
            "User asked for improvement without a measurable target. Either infer "
            "the most likely target from context and STATE it before acting, or "
            "ask which axis matters most (correctness, speed, clarity, size)."
        ),
        sources=[SRC_ANTHROPIC_BE_CLEAR, SRC_OPENAI_GUIDE, SRC_PROMPT_REPORT],
        check=rule_improve_without_metric,
        anthropic_ref="be-clear-and-direct",
    ),
    Rule(
        id="missing-guardrails",
        tier=1,
        name="Missing guardrails",
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
        guidance=(
            "User's prompt bundles multiple mutations. Propose an ordered plan "
            "with the smallest independently-verifiable slice first; ask which "
            "to skip if any."
        ),
        sources=[SRC_ANTHROPIC_CHAIN, SRC_PROMPT_REPORT],
        check=rule_compound_tasks,
        anthropic_ref="chain-complex-prompts",
    ),
    Rule(
        id="no-verify-loop",
        tier=2,
        name="No verify loop",
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
        guidance=(
            "User referenced an external artifact by role but not by ID. Ask "
            "for the identifier (issue #, test name, error string) before "
            "investigating, unless a single obvious candidate exists."
        ),
        sources=[SRC_ANTHROPIC_BE_CLEAR, SRC_CC_BESTPRACTICE],
        check=rule_missing_context_fetch,
        anthropic_ref="add-context-to-improve-performance",
    ),
    Rule(
        id="no-answer-shape",
        tier=1,
        name="Information ask without a shape",
        guidance=(
            "User asked an information-seeking question without specifying "
            "shape. Pick a compact default upfront (e.g. 'I'll give you 3 "
            "bullets each') and STATE it before answering; the user can "
            "redirect if the shape is wrong."
        ),
        sources=[SRC_OPENAI_GUIDE, SRC_ANTHROPIC_OVERVIEW, SRC_ANTHROPIC_BE_CLEAR],
        check=rule_no_answer_shape,
        anthropic_ref="control-the-format-of-responses",
    ),
    Rule(
        id="no-format-spec",
        tier=2,
        name="No output shape",
        guidance=(
            "User asked for structured output without specifying structure. Pick "
            "a compact default (bullets ≤ 7, or a small table) and STATE it "
            "before writing; user can redirect."
        ),
        sources=[SRC_OPENAI_GUIDE, SRC_ANTHROPIC_OVERVIEW],
        check=rule_no_format_spec,
        anthropic_ref="control-the-format-of-responses",
    ),
    # ---- L3 ----
    Rule(
        id="no-adversarial-check",
        tier=3,
        name="No adversarial check",
        guidance=(
            "User's prompt is high-stakes. Before acting, list 2–3 concrete "
            "failure modes and either address or explicitly accept each. Offer "
            "an adversarial-review pass."
        ),
        sources=[SRC_ANTHROPIC_CHAIN, SRC_PROMPT_REPORT, SRC_SIMONW],
        check=rule_no_adversarial_check,
        anthropic_ref="give-claude-a-role",
    ),
    Rule(
        id="retry-without-diagnosis",
        tier=3,
        name="Retry without diagnosis",
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
        guidance=(
            "User asked for pattern-matched output without providing an exemplar. "
            "Ask for one small example, or pick a plausible one from context and "
            "state your assumption explicitly before writing."
        ),
        sources=[SRC_ANTHROPIC_MULTISHOT, SRC_BROWN_FEWSHOT, SRC_PROMPT_REPORT],
        check=rule_no_few_shot,
        anthropic_ref="use-examples-effectively",
    ),
    Rule(
        id="no-chain-of-thought",
        tier=3,
        name="Hard reasoning without 'think first'",
        guidance=(
            "User asked a reasoning question. Think through the problem "
            "explicitly in your response (not silently) before stating the "
            "conclusion — restate the question, list what you know, then reason."
        ),
        sources=[SRC_ANTHROPIC_COT, SRC_WEI_COT, SRC_PROMPT_REPORT],
        check=rule_no_chain_of_thought,
        anthropic_ref="leverage-thinking-interleaved-thinking-capabilities",
    ),
    Rule(
        id="no-rubric",
        tier=3,
        name="Judgment without rubric",
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
        guidance=(
            "User asked an investigative question. When answering, distinguish "
            "verified findings from inference; if you can't confirm from the "
            "workspace/tools, say what you'd need to (a file, a run, a source) "
            "rather than guessing."
        ),
        sources=[SRC_ANTHROPIC_BE_CLEAR, SRC_SIMONW, SRC_CC_BESTPRACTICE],
        check=rule_no_uncertainty_budget,
        anthropic_ref="minimizing-hallucinations-in-agentic-coding",
    ),
    # ---- L4 goals & loops ----
    Rule(
        id="implicit-goal",
        tier=4,
        name="Action without goal",
        guidance=(
            "User's prompt has an action but no stated goal. State your best "
            "guess at the goal in one sentence and check it BEFORE acting; ask "
            "if there's a cheaper way to reach the same goal that skips the "
            "specified means."
        ),
        sources=[SRC_ANTHROPIC_BE_CLEAR, SRC_CC_BESTPRACTICE, SRC_PROMPT_REPORT],
        check=rule_implicit_goal,
        anthropic_ref="be-clear-and-direct",
    ),
    Rule(
        id="unbounded-iteration",
        tier=4,
        name="Loop without stopping condition",
        guidance=(
            "User asked for iterative refinement without a stopping condition. "
            "Propose an explicit exit criterion (test passes, rubric hit, N "
            "iterations, no new issues found) BEFORE the first round and "
            "confirm it."
        ),
        sources=[SRC_ANTHROPIC_CHAIN, SRC_PROMPT_REPORT, SRC_SIMONW],
        check=rule_unbounded_iteration,
        anthropic_ref="overthinking-and-excessive-thoroughness",
    ),
    Rule(
        id="no-rubric-for-refine",
        tier=4,
        name="Refinement without rubric",
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
        guidance=(
            "User asked for a risky change without asking for a plan. Before "
            "editing, propose an ordered plan (what changes, what stays, what "
            "the rollback is) and get one line of confirmation before "
            "executing."
        ),
        sources=[SRC_CC_BESTPRACTICE, SRC_CC_HOOKS, SRC_ANTHROPIC_CHAIN],
        check=rule_no_plan_mode_for_risky,
        anthropic_ref="balancing-autonomy-and-safety",
    ),
    Rule(
        id="no-task-list-for-multi-step",
        tier=5,
        name="Multi-step ask without a task list",
        guidance=(
            "User's prompt contains 3+ discrete actions. Use TaskCreate to "
            "materialize the steps up front, mark each in_progress as you "
            "start, and completed as you finish — this makes partial work "
            "visible."
        ),
        sources=[SRC_CC_BESTPRACTICE, SRC_CC_HOOKS],
        check=rule_no_task_list_for_multi_step,
        anthropic_ref="chain-complex-prompts",
    ),
    Rule(
        id="no-agents-for-parallel-lookup",
        tier=5,
        name="Multiple lookups without parallel agents",
        guidance=(
            "User implied multiple independent lookups. Fan them out with "
            "parallel Agent (Explore) calls in a single message rather than "
            "sequential Bash/Grep — same wall-clock, better coverage."
        ),
        sources=[SRC_CC_BESTPRACTICE, SRC_CC_HOOKS],
        check=rule_no_agents_for_parallel_lookup,
        anthropic_ref="optimize-parallel-tool-calling",
    ),
    Rule(
        id="no-role-for-critique",
        tier=5,
        name="Review ask without a role",
        guidance=(
            "User asked for a review without specifying a persona. Ask which "
            "lens (correctness / security / API / readability / performance) — "
            "then invoke or emulate that role explicitly rather than doing a "
            "generic pass."
        ),
        sources=[SRC_CC_BESTPRACTICE, SRC_ANTHROPIC_CHAIN, SRC_SIMONW],
        check=rule_no_role_for_critique,
        anthropic_ref="give-claude-a-role",
    ),
    Rule(
        id="no-panel-for-contested-design",
        tier=5,
        name="Contested design without a panel",
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
        guidance=(
            "User implied fan-out over many items. Propose parallel agent "
            "fan-out or Workflow orchestration BEFORE starting; a serial for-"
            "each loop should be the fallback, not the default."
        ),
        sources=[SRC_CC_BESTPRACTICE, SRC_CC_HOOKS],
        check=rule_no_workflow_for_fanout,
        anthropic_ref="subagent-orchestration",
    ),
    Rule(
        id="incremental-routing",
        tier=5,
        name="Routing a multi-step task one step at a time",
        guidance=(
            "User is driving a multi-step task one terse step at a time "
            "('continue', 'one after another', 'do the next one'). Every step "
            "costs a human round-trip and re-establishes context. Offer to "
            "decompose the remaining work once into a TaskCreate checklist (or "
            "a Workflow for a big fan-out), then run the sequence autonomously "
            "with a verification gate — don't route per step."
        ),
        sources=[SRC_ANTHROPIC_CHAINCOMPLEX, SRC_CC_BESTPRACTICE,
                 SRC_LANGCHAIN_PLANEXEC],
        check=rule_incremental_routing,
        anthropic_ref="chain-complex-prompts",
    ),
    # ---- L6 skill-awareness ----
    Rule(
        id="no-skill-lookup",
        tier=6,
        name='"How do I …" without checking existing skills',
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
        guidance=(
            "User described a repeatable multi-step workflow ('first X, then "
            "Y, then Z', 'every time we do this…'). Offer to draft a skill "
            "scaffold (SKILL.md with frontmatter, steps, verification). Point "
            "at the alexmskills patterns if the user has that plugin family."
        ),
        sources=[SRC_MCILROY_UNIX, SRC_ANTHROPIC_SKILLS, SRC_FOWLER_REFACTOR],
        check=rule_no_skill_composition,
    ),
    # ---- v0.20.0 — Anthropic-guide gap closers ----
    Rule(
        id="no-xml-structure",
        tier=3,
        name="Pasted content without XML tags",
        guidance=(
            "User pasted substantial content (≥8 lines of code fence or "
            "indented block) without XML tags. Suggest wrapping it — Anthropic "
            "recommends XML delimiters for reliable parsing of long reference "
            "content. Names the specific tags that fit the material."
        ),
        sources=[SRC_ANTHROPIC_XML, SRC_ANTHROPIC_BE_CLEAR, SRC_CC_BESTPRACTICE],
        check=rule_no_xml_structure,
        anthropic_ref="structure-prompts-with-xml-tags",
    ),
    Rule(
        id="no-classical-role",
        tier=3,
        name="Critique/review ask without a role",
        guidance=(
            "User asked for review / audit / critique in a medium-long prompt "
            "with no 'you are a X' role framing. Suggest a role that fits the "
            "domain (security, performance, correctness, etc.). Distinct from "
            "the Claude-Code `/roles:as` rule — this is the classical inline "
            "role-priming technique."
        ),
        sources=[SRC_ANTHROPIC_ROLE, SRC_CC_BESTPRACTICE, SRC_PROMPT_REPORT],
        check=rule_no_classical_role,
        anthropic_ref="give-claude-a-role",
    ),
    Rule(
        id="test-goalseeking",
        tier=3,
        name="Test-passing without correctness",
        guidance=(
            "User asked to 'make tests pass' / 'fix broken tests' / 'get CI "
            "green' without stating the correctness intent. Anthropic's guide "
            "flags this as a hallucination/gaming vector: Claude may skip, "
            "mock, or hard-code around real bugs. Reframe the ask around what "
            "SHOULD be true; use tests as verification, not the goal."
        ),
        sources=[SRC_ANTHROPIC_TESTGAME, SRC_ANTHROPIC_HALLUCINATE, SRC_CC_BESTPRACTICE],
        check=rule_test_goalseeking,
        anthropic_ref="avoid-focusing-on-passing-tests-and-hard-coding",
    ),
    Rule(
        id="no-verify-before-claim",
        tier=3,
        name="Assertion ask without evidence demand",
        guidance=(
            "User asked an assertion-shaped question about the workspace "
            "('does X exist', 'is Y used', 'which files reference Z') without "
            "demanding receipts (file:line, quoted code). This is where "
            "hallucinations hide in agentic coding. When answering, cite "
            "concrete file paths and line ranges; if you can't find evidence, "
            "say so explicitly rather than inferring."
        ),
        sources=[SRC_ANTHROPIC_HALLUCINATE, SRC_CC_BESTPRACTICE, SRC_SIMONW],
        check=rule_no_verify_before_claim,
        anthropic_ref="minimizing-hallucinations-in-agentic-coding",
    ),
    Rule(
        id="overthinking-warning",
        tier=4,
        name="Over-elaborated ask",
        guidance=(
            "User's prompt has 3+ overthinking/thoroughness markers ('make "
            "sure to', 'be very careful', 'please also', 'every single', "
            "etc.) in a long prompt. Anthropic's guide flags this as a "
            "wasteful pattern — Claude matches the energy and over-scopes. "
            "Push toward the smallest ask that still gets the outcome."
        ),
        sources=[SRC_ANTHROPIC_OVERTHINK, SRC_ANTHROPIC_OVEREAGER, SRC_CC_BESTPRACTICE],
        check=rule_overthinking_warning,
        anthropic_ref="overthinking-and-excessive-thoroughness",
    ),
    Rule(
        id="no-edit-preference",
        tier=6,
        name="Create-new without edit-existing preference",
        guidance=(
            "User asked to create a new file/script/helper without stating an "
            "edit-existing preference. Anthropic's 'Reduce file creation' "
            "guidance is explicit: prefer editing. Before creating anything, "
            "look for an existing file that could be extended; only create "
            "new if nothing fits."
        ),
        sources=[SRC_ANTHROPIC_FILECREATE, SRC_CC_BESTPRACTICE, SRC_MCILROY_UNIX],
        check=rule_no_edit_preference,
        anthropic_ref="reduce-file-creation-in-agentic-coding",
    ),
]

RULES_BY_ID = {r.id: r for r in RULES}


# ---------------------------------------------------------------------------
# v0.28.0 — Proactive tips (advanced-technique suggestions)
# ---------------------------------------------------------------------------
# Rules are reactive: they fire when your prompt has a problem. Tips are
# proactive: they fire when your prompt is on-topic for an advanced technique
# you could have used to get a better result. Tips never dispute your prompt
# — they suggest an addition next time.
#
# Firing:
#   - Only when NO rule fired this prompt (nudge wins over tip)
#   - Rate-limited: per-tip cooldown of `tip_cooldown_prompts` prompts
#   - Variable-ratio: 1 out of `tip_ratio` matching prompts fires (Skinner)
#   - Skipped: conversational, picker-answer, task-notification prompts
#
# Visual: 💡 (light bulb) — distinct from 🎯 (rules) and ✨ (praise).
# Log outcome: `tipped:<style>:<tip-id>`

@dataclass
class Tip:
    id: str                              # kebab-case, prefixed 'tip-'
    technique: str                       # short name of the technique
    body: str                            # colleague-voice suggestion with concrete example
    guidance: str                        # short hint for Claude's additionalContext
    sources: list[tuple[str, str]]       # (title, url)
    check: Callable[[str], bool]         # heuristic: is this prompt on-topic?


def _tip_few_shot_check(prompt: str) -> bool:
    pl = prompt.lower()
    words = pl.split()
    if len(words) < 8:
        return False
    # Support "write me a X" (with "me") and "write a X" (without)
    creative_action = re.search(
        r"\b(write|generate|create|draft|compose|come up with)\s+"
        r"(?:me\s+)?"
        r"(?:a\s+|an\s+|some\s+)?"
        r"(poem|blog\s+post|essay|description|name|slogan|tagline|"
        r"headline|caption|story|paragraph|summary|title)\b", pl)
    if not creative_action:
        return False
    # Already has an example — no tip needed
    if re.search(r"\b(like this|for example|example:|e\.g\.\b|"
                  r"in the style of)\b", pl):
        return False
    return True


def _tip_xml_tags_check(prompt: str) -> bool:
    # Small paste (3-6 lines of code fence or indented) that no-xml-structure
    # (which requires ≥7) doesn't catch. Meaningful enough to benefit from
    # delimiting but currently unwrapped.
    lines = prompt.splitlines()
    max_indented_run = 0
    run = 0
    for line in lines:
        if line.startswith("    ") or line.startswith("\t"):
            run += 1
            max_indented_run = max(max_indented_run, run)
        else:
            run = 0
    fence_lines = 0
    in_fence = False
    for line in lines:
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            fence_lines += 1
    paste = max(max_indented_run, fence_lines)
    if not (3 <= paste <= 6):
        return False
    has_tag = re.search(r"<[a-z][\w-]*(?:\s+[^>]*)?>", prompt, re.IGNORECASE)
    return not bool(has_tag)


def _tip_classical_role_check(prompt: str) -> bool:
    words = prompt.split()
    # Fires on SHORT review asks (5-14 words) that no-classical-role skips.
    if not (5 <= len(words) < 15):
        return False
    pl = prompt.lower()
    is_review = re.search(r"\b(review|audit|critique|check|look at)\b", pl)
    if not is_review:
        return False
    has_role = re.search(
        r"\b(you are (?:a|an|the)|act as|your role is|"
        r"take the role of|pretend you'?re)\b", pl)
    return not bool(has_role)


def _tip_plan_mode_check(prompt: str) -> bool:
    words = prompt.split()
    # 4-14 words: too short for no-plan-mode-for-risky (which wants more
    # context) but risky enough to benefit from a plan-first suggestion.
    if not (4 <= len(words) < 15):
        return False
    pl = prompt.lower()
    risky = re.search(
        r"\b(refactor|rewrite|migrate|delete\s+all|drop\s+(table|column)|"
        r"deploy\s+to\s+prod|schema\s+change)\b", pl)
    if not risky:
        return False
    has_plan = re.search(r"\b(plan (?:first|it|this)|propose (?:a )?plan|"
                          r"/plan|first (?:propose|sketch))\b", pl)
    return not bool(has_plan)


def _tip_chain_of_thought_check(prompt: str) -> bool:
    words = prompt.split()
    if len(words) < 6:
        return False
    pl = prompt.lower()
    # Explanation / reasoning ask that no-chain-of-thought (which requires
    # specific reasoning verbs like "debug"/"trace") doesn't catch.
    is_explain = re.search(
        r"\b(explain\s+why|walk me through|help me understand|"
        r"how does this|why is|why does)\b", pl)
    if not is_explain:
        return False
    has_cot = re.search(r"\b(think (?:it |this )?through|step by step|"
                         r"reason (?:step by step|carefully)|"
                         r"take your time)\b", pl)
    return not bool(has_cot)


def _tip_verify_loop_check(prompt: str) -> bool:
    # Small implementation ask (4-14 words) where no-verify-loop's threshold
    # doesn't apply. Anything shorter is likely a followup; anything longer
    # is caught by the L2 rule.
    words = prompt.split()
    if not (4 <= len(words) < 15):
        return False
    pl = prompt.lower()
    impl = re.search(
        r"\b(implement|add|create|write|build)\b.*"
        r"\b(function|method|endpoint|route|handler|class|component)\b",
        pl)
    if not impl:
        return False
    verify = re.search(
        r"\b(run (?:the )?tests|and (?:the )?tests? pass|verify|confirm|"
        r"until (?:it )?works)\b", pl)
    return not bool(verify)


TIPS: list[Tip] = [
    Tip(
        id="tip-few-shot",
        technique="Show an example",
        body=(
            "Creative generation lands better with a 1-2 line example of the "
            "style you want. Try adding `like this: <sample>` or `in the "
            "style of <thing>` — few-shot beats description almost every time."
        ),
        guidance=(
            "User asked for creative generation without an example. In your "
            "response, either (a) produce your best guess and note that a "
            "sample would tighten the aim, or (b) ask for one short example "
            "of the style they want before generating."
        ),
        sources=[SRC_ANTHROPIC_MULTISHOT, SRC_BROWN_FEWSHOT],
        check=_tip_few_shot_check,
    ),
    Tip(
        id="tip-xml-tags",
        technique="Delimit pasted content with XML tags",
        body=(
            "Even short pastes read cleaner in `<code>...</code>` or "
            "`<data>...</data>` tags — clear boundary between content and "
            "instructions. Optional for a 3-line snippet, but the habit "
            "scales."
        ),
        guidance=(
            "User pasted a small block without XML delimiters. In your "
            "response, treat the paste correctly; you don't need to demand "
            "tags on this ask, just note the technique."
        ),
        sources=[SRC_ANTHROPIC_XML],
        check=_tip_xml_tags_check,
    ),
    Tip(
        id="tip-classical-role",
        technique="Give the reviewer a role",
        body=(
            "Short review asks are hit-or-miss without a role. Add one line "
            "at the top: `you are a senior security engineer` (or "
            "`performance-obsessed`, `skeptical of premature abstraction`) — "
            "the persona shapes what gets caught."
        ),
        guidance=(
            "User asked for a review without invoking a role. Do the review "
            "normally; suggest role-priming as a next-time habit, don't "
            "block."
        ),
        sources=[SRC_ANTHROPIC_ROLE],
        check=_tip_classical_role_check,
    ),
    Tip(
        id="tip-plan-mode",
        technique="Sketch the plan first for risky changes",
        body=(
            "Refactors / migrations / deletes usually benefit from a plan "
            "pass before code. Try: `propose a plan first (don't touch "
            "code), then I'll green-light`. Or use `/plan` if your CLI has "
            "it."
        ),
        guidance=(
            "User asked for a risky change in a short prompt. Consider "
            "proposing a plan first even though they didn't ask for it, "
            "or ask if they want a plan pass before you dive in."
        ),
        sources=[SRC_ANTHROPIC_AUTONOMY, SRC_CC_BESTPRACTICE],
        check=_tip_plan_mode_check,
    ),
    Tip(
        id="tip-chain-of-thought",
        technique="Ask for step-by-step reasoning",
        body=(
            "For explanation / why questions, add `think it through step "
            "by step` — chain-of-thought is a well-known accuracy lift on "
            "reasoning tasks. Costs a bit more output; pays off in "
            "correctness."
        ),
        guidance=(
            "User asked an explanation question without a think-first "
            "clause. Answer thoroughly; walking through your reasoning "
            "explicitly is worth doing here even if they didn't ask."
        ),
        sources=[SRC_ANTHROPIC_COT, SRC_WEI_COT],
        check=_tip_chain_of_thought_check,
    ),
    Tip(
        id="tip-verify-loop",
        technique="Add a verification step",
        body=(
            "For implementation asks, add `and run the tests` or `and "
            "confirm the build stays green`. Closes the loop — no ambiguity "
            "about whether the change actually works."
        ),
        guidance=(
            "User asked for an implementation without a verification "
            "clause. After the change, run the relevant tests / type-check "
            "/ build and report the result even if not asked."
        ),
        sources=[SRC_CC_BESTPRACTICE, SRC_ANTHROPIC_BE_CLEAR],
        check=_tip_verify_loop_check,
    ),
]

TIPS_BY_ID = {t.id: t for t in TIPS}

# v0.28.0 — Mode B: graduation-triggered scaffolding. When an L1/L2 rule
# masters, unlock a paired tip pointing at a related next-level technique.
# The learning sequence is baked in here — fundamentals mastered ⇒ nudge
# toward advanced technique they haven't tried yet.
_TIP_ON_MASTERY: dict[str, str] = {
    "vague-reference":         "tip-few-shot",
    "no-definition-of-done":   "tip-verify-loop",
    "missing-guardrails":      "tip-plan-mode",
    "unbounded-scope":         "tip-chain-of-thought",
    "improve-without-metric":  "tip-classical-role",
    "no-answer-shape":         "tip-xml-tags",
}


def _pick_matching_tip(prompt: str, cfg: dict, g: dict) -> str | None:
    """v0.28.0 — Mode A: standalone matching. Returns the id of a tip whose
    heuristic matches the prompt AND is off cooldown AND wins the variable-
    ratio dice roll. None otherwise.

    Never fires when a rule already fired on this prompt (nudge > tip);
    caller enforces that by only calling when nothing else fired.
    """
    if not bool(cfg.get("tips_enabled", True)):
        return None
    cooldown = int(cfg.get("tip_cooldown_prompts", 100))
    ratio = max(1, int(cfg.get("tip_ratio", 5)))
    prompt_count = int(g.get("prompt_count", 0))
    tips_state = g.setdefault("tips", {})
    for tip in TIPS:
        if not tip.check(prompt):
            continue
        st = tips_state.get(tip.id, {}) or {}
        last = int(st.get("last_fired_prompt", 0))
        if last > 0 and prompt_count - last < cooldown:
            continue
        # Variable-ratio: fires every ratio-th matching + cooldown-clear
        # opportunity per tip. Uses fires_total as the counter so it's
        # deterministic per tip.
        opportunity = int(st.get("opportunities_total", 0)) + 1
        st["opportunities_total"] = opportunity
        tips_state[tip.id] = st
        if opportunity % ratio == 0:
            return tip.id
    return None


def _record_tip_fire(g: dict, tip_id: str) -> None:
    """Track that a tip fired for cooldown + stats."""
    tips_state = g.setdefault("tips", {})
    st = tips_state.get(tip_id, {}) or {}
    st["fires_total"] = int(st.get("fires_total", 0)) + 1
    st["last_fired_at"] = _now_iso()
    st["last_fired_prompt"] = int(g.get("prompt_count", 0))
    tips_state[tip_id] = st
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


# ---- v0.40.0 — positive detectors for the 13 rules that previously had no
# mirror. Every rule now has one so mastery can be *earned* by demonstrating
# the good technique, not merely by not tripping the rule. ------------------

def pos_batched_routing(prompt: str) -> bool:
    """Mirrors incremental-routing: user batched the steps up front (task
    list / numbered plan / workflow) instead of routing one at a time."""
    pl = prompt.lower()
    worded = re.search(
        r"\b(task ?list|checklist|as a workflow|use taskcreate|taskcreate|"
        r"do all of (?:these|the following|them)|here'?s the plan|"
        r"batch (?:these|them)|all at once|in parallel)\b", pl)
    numbered = len(re.findall(r"(?m)^\s*\d+[.)]\s+\S", prompt)) >= 2
    return bool(worded or numbered)


def pos_structured_tasks(prompt: str) -> bool:
    """Mirrors compound-tasks: 3+ actions, but laid out as a list / task
    list / first-then sequence instead of an 'and'-chain."""
    n = len(re.findall(rf"\b(?:{'|'.join(ACTION_VERBS)})\b", prompt.lower()))
    if n < 3:
        return False
    return bool(len(re.findall(r"(?m)^\s*(?:\d+[.)]|[-*])\s+\S", prompt)) >= 2
                or re.search(r"\b(task ?list|checklist|step 1|use taskcreate)\b"
                             r"|first\b.*\bthen\b", prompt.lower()))


def pos_asked_adversarial(prompt: str) -> bool:
    """Mirrors no-adversarial-check: user invited a skeptical / red-team pass."""
    return bool(re.search(
        r"\b(adversarial|red[- ]team|devil'?s advocate|skeptic|poke holes|"
        r"what could go wrong|try to break (?:this|it)|attack this|"
        r"steelman|challenge (?:this|it|the))\b", prompt.lower()))


def pos_assigned_role(prompt: str) -> bool:
    """Mirrors no-classical-role: user gave Claude a role/persona."""
    return bool(re.search(
        r"\b(you are an? |act as an? |as an? expert |play the role of|"
        r"imagine you are|assume the role|in the role of)\b", prompt.lower()))


def pos_preferred_edit(prompt: str) -> bool:
    """Mirrors no-edit-preference: user preferred editing existing code over
    creating new files."""
    return bool(re.search(
        r"\b(edit (?:the )?existing|modify (?:the )?existing|"
        r"update (?:the )?existing|extend (?:the )?existing|in[- ]?place|"
        r"don'?t create (?:a )?new|reuse (?:the )?existing|"
        r"add (?:it )?to (?:the )?existing)\b", prompt.lower()))


def pos_refine_with_axis(prompt: str) -> bool:
    """Mirrors no-rubric-for-refine: refine ask that names the axis."""
    pl = prompt.lower()
    refine = re.search(r"\b(refine|improve|polish|tighten|revise|rework)\b", pl)
    axis = re.search(
        r"\b(for readability|for clarity|for performance|for correctness|"
        r"for maintainability|specifically the|the error handling|the naming|"
        r"the structure|on the .{0,20} (?:axis|dimension)|in terms of)\b", pl)
    return bool(refine and axis)


def pos_named_skill_candidate(prompt: str) -> bool:
    """Mirrors no-skill-composition: user named a repeatable ceremony as a
    skill candidate."""
    return bool(re.search(
        r"\b(make (?:this|it) a skill|turn (?:this|it) into a skill|"
        r"add a skill for|as a reusable skill|create a skill|"
        r"skill candidate|worth a skill|should be a skill)\b", prompt.lower()))


def pos_demanded_receipts(prompt: str) -> bool:
    """Mirrors no-verify-before-claim: user demanded evidence, not assertion."""
    return bool(re.search(
        r"\b(cite (?:the )?file|file:line|with (?:the )?line numbers?|"
        r"quote the (?:code|line)|show me where|point to the (?:exact )?\w+|"
        r"with evidence|don'?t guess|verify before|receipts?\b)\b",
        prompt.lower()))


def pos_used_xml_tags(prompt: str) -> bool:
    """Mirrors no-xml-structure: user delimited pasted content with tags."""
    return bool(re.search(
        r"<(code|data|logs?|context|document|example|input|file|error|"
        r"output|instructions?)>", prompt, re.I))


def pos_asked_concise(prompt: str) -> bool:
    """Mirrors overthinking-warning: user explicitly asked to keep it simple."""
    return bool(re.search(
        r"\b(keep it (?:simple|brief|short)|don'?t overthink|be concise|"
        r"briefly|one[- ]liner|minimal (?:change|diff)|smallest change|"
        r"just the\b)\b", prompt.lower()))


def pos_diagnosed_retry(prompt: str) -> bool:
    """Mirrors retry-without-diagnosis: a retry carrying new information."""
    pl = prompt.lower()
    retry = re.search(
        r"\b(try again|retry|still (?:failing|broken|not)|"
        r"another (?:attempt|approach))\b", pl)
    diagnosis = re.search(
        r"\b(because|the error (?:was|is)|it failed (?:on|because|with)|"
        r"the issue (?:was|is)|root cause|this time|the reason|turns out|"
        r"i think it'?s)\b", pl)
    return bool(retry and diagnosis)


def pos_stated_correctness_intent(prompt: str) -> bool:
    """Mirrors test-goalseeking: 'make tests pass' plus a correctness intent
    that forecloses hard-coding / gaming."""
    pl = prompt.lower()
    tests = re.search(
        r"\b(tests? pass|ci green|fix (?:the )?(?:broken )?tests?|make .{0,20}pass)\b", pl)
    intent = re.search(
        r"\b(without (?:changing|breaking) behavior|hard[- ]?cod(?:e|ing)|"
        r"fix the (?:actual|real|root) (?:bug|cause|issue)|"
        r"without cheating|keep the behavior|real fix|properly)\b", pl)
    return bool(tests and intent)


def pos_stated_answer_shape(prompt: str) -> bool:
    """Mirrors no-answer-shape: a question that specifies the answer format."""
    pl = prompt.lower()
    question = "?" in prompt or re.search(
        r"\b(what|which|how many|how much|list|name)\b", pl)
    shape = re.search(
        r"\b(as a (?:table|list|bullet)|in json|one[- ]word|in a table|"
        r"a single (?:number|word|sentence)|yes or no|comma[- ]separated|"
        r"top \d+|ranked)\b", pl)
    return bool(question and shape)


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
    # ---- v0.40.0 — mirrors for the 13 previously-unmirrored rules ----
    Positive("batched-routing", "incremental-routing", 5,
             pos_batched_routing, [
                 "You batched the steps up front instead of routing one at a time. That's one plan, not ten round-trips.",
                 "A task list / plan instead of 'continue'×10. The agent runs the whole thing while you get coffee.",
             ], [SRC_BROPHY_PRAISE, SRC_FOGG_TINY]),
    Positive("structured-tasks", "compound-tasks", 2,
             pos_structured_tasks, [
                 "You laid the multi-part ask out as a list, not an 'and'-chain. Nothing gets dropped now.",
                 "Structured the steps instead of run-on-sentencing them. Each one has a home.",
             ], [SRC_BROPHY_PRAISE, SRC_MUELLER_DWECK]),
    Positive("asked-adversarial", "no-adversarial-check", 3,
             pos_asked_adversarial, [
                 "You invited a skeptical pass on a high-stakes ask. Red-teaming your own plan is a senior move.",
                 "You asked Claude to poke holes. Better it finds them than prod does.",
             ], [SRC_BROPHY_PRAISE, SRC_DECI_RYAN]),
    Positive("assigned-role", "no-classical-role", 3,
             pos_assigned_role, [
                 "You gave Claude a role — the answer will speak from that expertise instead of hedging generically.",
                 "'You are a X' framing. Sharper lens, sharper answer.",
             ], [SRC_BROPHY_PRAISE, SRC_FOGG_TINY]),
    Positive("preferred-edit", "no-edit-preference", 6,
             pos_preferred_edit, [
                 "You asked to edit existing code rather than spawn a new file. Fewer orphans, less sprawl.",
                 "Edit-in-place over new-file. The repo stays a repo, not a landfill.",
             ], [SRC_FOWLER_REFACTOR, SRC_BROPHY_PRAISE]),
    Positive("refine-with-axis", "no-rubric-for-refine", 4,
             pos_refine_with_axis, [
                 "You named the axis to refine on. 'Better' is now a direction, not a vibe.",
                 "Refine + a specific dimension. Claude knows which way is up.",
             ], [SRC_BROPHY_PRAISE, SRC_DECI_RYAN]),
    Positive("named-skill-candidate", "no-skill-composition", 6,
             pos_named_skill_candidate, [
                 "You named a repeatable ceremony as a skill candidate. That's the composition instinct paying off.",
                 "Spotted a skill hiding in a routine. Future-you will invoke it in one line.",
             ], [SRC_FOWLER_REFACTOR, SRC_ANTHROPIC_SKILLS]),
    Positive("demanded-receipts", "no-verify-before-claim", 3,
             pos_demanded_receipts, [
                 "You demanded receipts — file:line, quoted code — instead of taking an assertion on faith.",
                 "'Show me where' beats 'does X exist?'. Hallucinations don't survive evidence.",
             ], [SRC_BROPHY_PRAISE, SRC_DECI_RYAN]),
    Positive("used-xml-tags", "no-xml-structure", 3,
             pos_used_xml_tags, [
                 "You delimited the pasted content with tags. Claude can tell your data from your instructions now.",
                 "Tagged the payload. No more 'wait, was that line part of the code or the ask?'.",
             ], [SRC_BROPHY_PRAISE, SRC_MUELLER_DWECK]),
    Positive("asked-concise", "overthinking-warning", 4,
             pos_asked_concise, [
                 "You asked to keep it simple. Sometimes the best prompt engineering is a shorter prompt.",
                 "'Don't overthink it.' The rare nudge toward less structure — and the right one here.",
             ], [SRC_FOGG_TINY, SRC_BROPHY_PRAISE]),
    Positive("diagnosed-retry", "retry-without-diagnosis", 3,
             pos_diagnosed_retry, [
                 "Your retry carried new information — the error, the cause, the change. That's a retry that can actually converge.",
                 "You didn't just say 'try again', you said why. The loop has a chance now.",
             ], [SRC_BROPHY_PRAISE, SRC_DECI_RYAN]),
    Positive("stated-correctness-intent", "test-goalseeking", 3,
             pos_stated_correctness_intent, [
                 "You paired 'make it pass' with a correctness intent. No hard-coding the green checkmark.",
                 "You foreclosed the cheat — real fix, not a mocked one. The tests still mean something.",
             ], [SRC_BROPHY_PRAISE, SRC_DECI_RYAN]),
    Positive("stated-answer-shape", "no-answer-shape", 1,
             pos_stated_answer_shape, [
                 "You specified the answer shape — table, JSON, one word. You'll get what you can use, first try.",
                 "You told Claude the format up front. No reformatting round-trip.",
             ], [SRC_BROPHY_PRAISE, SRC_FOGG_TINY]),
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
    A cooldown of 0 disables mastered firing entirely.
    v0.27.0: `inactive` status (rule graduated with fires_total == 0)
    behaves like `mastered` for slot-freeing — the rule doesn't apply to
    the user's patterns, so it shouldn't block newer rules from activating.
    But it does NOT get refresher fires or count in mastery stats."""
    practicing: list[str] = []
    mastered: list[str] = []
    # v0.41.0 (Proposal 2) — precision-gated activation. A rule the user
    # consistently rejects is demoted to `dormant` (suppressed from firing),
    # generalizing the mastery `inactive` status to *dismissed* rules — the
    # path static-analysis research endorses over hard-disabling. A small
    # deterministic explore slot periodically re-surfaces one dormant rule so
    # a rule that was noisy in only one context isn't buried forever
    # (exploit/explore, ~1-in-explore_period).
    min_outcomes = int(cfg.get("min_outcomes_for_gating", 4))
    floor = float(cfg.get("precision_floor", 0.15))
    gate_on = bool(cfg.get("precision_gating", True))
    dormant: list[str] = []
    for rid in RULE_ORDER:
        if rid in cfg.get("disabled_rules", []):
            continue
        st = effective_status(rid, g, l)
        if st == "mastered":
            mastered.append(rid)
            continue
        if st == "inactive":
            # Frees the slot but doesn't participate in mastered refreshers.
            continue
        # Practicing candidate — apply the precision gate.
        if gate_on:
            prec = _rule_precision(g.get("rules", {}).get(rid, {}), min_outcomes)
            if prec is not None and prec < floor:
                dormant.append(rid)
                continue
        practicing.append(rid)
    # Explore slot: periodically re-admit one dormant rule to refresh its
    # precision estimate. Deterministic (keyed off prompt_count) so it's
    # testable and resume-safe.
    explore_period = int(cfg.get("explore_period", 10))
    pc = int(g.get("prompt_count", 0))
    if dormant and explore_period > 0 and pc % explore_period == 0:
        practicing.append(dormant[(pc // explore_period) % len(dormant)])
    max_active = int(cfg.get("max_active_rules", 5))
    if len(practicing) > max_active:
        def rank(rid: str) -> tuple:
            r = RULES_BY_ID[rid]
            rs = g.get("rules", {}).get(rid, {})
            fires = rs.get("fires_total", 0)
            # Prefer higher precision (unknown precision sorts neutral at 1.0
            # so unproven rules still get their fair chance to accrue data).
            prec = _rule_precision(rs, min_outcomes)
            prec = 1.0 if prec is None else prec
            return (r.tier, -round(prec, 3), -fires, RULE_ORDER.index(rid))
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


# ---------------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# v0.34.0 — collaborator mode (C+D architecture)
# ---------------------------------------------------------------------------
# Instead of emitting a hand-written nudge and hoping the user rewrites their
# own prompt, we tell Claude — same turn, same response — to do the analysis
# and produce an improved rewrite. Claude has full session context via the
# transcript, so it can veto false positives (context resolves it) and
# produce a situated improvement.
#
# No external API call. No latency. Uses the exact model the user is already
# paying for on this turn. Data flow: the prompt already goes to Claude to be
# answered; we just piggyback a "coach analysis" job onto the same response.

_V34_INSTRUCTION_TEMPLATE = """[prompt-coach · v0.34 · collaborator mode]

The user just submitted this prompt:
«{prompt_text}»

The coach's regex fast-filter identified these candidate rules that MIGHT
apply to this prompt (rule id · one-line concept · Anthropic guide anchor):

{candidate_rules_block}

Read the last few turns of our conversation as context. Then, in this
same response, do the following BEFORE addressing the user's actual
question:

1. Decide which candidate rules actually apply given full context. Rules
   whose concern is resolved by prior context (e.g. "vague-reference"
   for "it" when "it" was named two turns ago) go into `vetoed`.
2. Write an improved version of the user's prompt that addresses the
   confirmed rules. Don't add improvements NOT backed by a candidate
   rule — this coach is opinionated, anchored to specific concepts.
3. List 1-3 specific changes you made, one line each.
4. In the Sources line, cite {sources_instruction}.

Render the coach block at the very start of your response, verbatim,
following this format:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💬 prompt-coach — I read your prompt as:

    "<your improved version of the user's prompt>"

Changes:
  [1] <one-line change with the rule concept in parens>
  [2] <second change if any>
  [3] <third change if any>

Sources: <one per confirmed rule, per the Sources instruction above>

Reply "yes" to proceed with this rewrite, "no" for original, or
"edit" to change something.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Then, below the block, address the user's actual question using
your best judgment about which prompt to work from — default to the
improved version unless the user's original had a specific
constraint the rewrite loses.

Guardrails:
- If your confidence that any candidate rule actually applies is LOW
  (context resolves everything), skip the coach block entirely and
  just answer the question. Silence is better than a false-positive
  rewrite.
- Match the user's voice: brief if they're brief, expansive if they're
  detailed. Don't preach.
- The coach is opinionated — every change must trace to one of the
  candidate rules above. No freewheeling improvements.
- User's next turn is their signal:
    "yes" / "y" / "ok"  → they accept your rewrite; you already
                          proceeded correctly.
    "no" / "n"          → they preferred the original; on your NEXT
                          response, reset to the original and proceed.
    "edit <thing>"      → adjust the rewrite as they specify.

  You don't need to record this — the coach's next-turn analyzer will
  read your rendered coach block from the transcript and infer the
  signal.

Your response starts NOW, with either the coach block or (if
confidence too low) directly with the answer to the user's question."""


def _anthropic_url(ref: str | None) -> str | None:
    """v0.36.0 — resolve an anthropic_ref anchor slug to a full doc URL.
    Returns None when the rule has no upstream mapping."""
    if not ref:
        return None
    return f"{_ANTHROPIC_BEST}#{ref}"


def _v34_candidate_rules_block(rule_ids: list[str],
                               show_urls: bool = True) -> str:
    """Render a compact one-rule-per-line block with concept + anthropic_ref.
    Used inside the v0.34 additionalContext instruction so Claude has enough
    to reason about which rules apply without needing to look up the full
    catalog.

    v0.36.0 — when show_urls is on, append the full doc URL for each rule so
    Claude can render a clickable Sources line (terminals auto-linkify a bare
    https URL; the user Cmd/Ctrl-clicks to open the docs)."""
    lines = []
    for rid in rule_ids:
        r = RULES_BY_ID.get(rid)
        if not r:
            continue
        ref = r.anthropic_ref or "(no upstream mapping)"
        url = _anthropic_url(r.anthropic_ref)
        if show_urls and url:
            lines.append(f"  · {r.id:32s} — {r.name} · {ref} · {url}")
        else:
            lines.append(f"  · {r.id:32s} — {r.name} · {ref}")
    return "\n".join(lines) if lines else "  (none — this shouldn't happen)"


def _v34_context_for_claude(prompt_text: str, rule_ids: list[str],
                            show_urls: bool = True) -> str:
    """Build the v0.34 additionalContext instruction telling Claude to run
    the coach analysis inline as part of its response."""
    sources_instruction = (
        "the FULL clickable doc URL shown for each confirmed rule in the "
        "candidate list above (render the bare https URL so the terminal "
        "linkifies it)"
        if show_urls else
        "the Anthropic guide anchor slug for each confirmed rule (see the "
        "anchors above; use the exact strings)"
    )
    return _V34_INSTRUCTION_TEMPLATE.format(
        prompt_text=prompt_text[:2000],
        candidate_rules_block=_v34_candidate_rules_block(rule_ids, show_urls),
        sources_instruction=sources_instruction,
    )


def _ack_line(g: dict, active_practicing: list[str], threshold: int,
              min_demonstrations: int = 3,
              demonstrated: list[str] | None = None) -> str:
    """v0.41.1 — build the compact clean-prompt acknowledgment line, made
    *specific*: it names the rule involved rather than emitting a bare count
    ("watching 1 rule" told you nothing). Priority of what to surface:

    1. If THIS prompt demonstrated a good technique (a positive fired), say
       which rule it satisfied + progress toward mastery — the most
       informative signal ("what did I just do right?").
    2. Else, the practicing rule closest to mastery (has ≥1 demonstration).
    3. Else, NAME the rules being watched (not a count) so it's actionable.
    4. Else, all active rules mastered.
    """
    rules = g.get("rules", {})
    demonstrated = [r for r in (demonstrated or []) if r in rules or r]

    # 1) Most informative: the prompt actively USED a good technique.
    if demonstrated:
        best = max(demonstrated,
                   key=lambda rid: int(rules.get(rid, {}).get("demonstrations", 0)))
        d = int(rules.get(best, {}).get("demonstrations", 0))
        if rules.get(best, {}).get("status") == "mastered":
            return f"✓ prompt-coach · clean prompt · you used {best} (mastered 🎓)"
        return (f"✓ prompt-coach · clean prompt · you used {best} "
                f"({min(d, min_demonstrations)}/{min_demonstrations} toward mastery)")

    # 2)/3) rank the active practicing rules.
    masterable = []          # (rid, demonstrations) — on the mastery path
    watching: list[str] = []
    for rid in active_practicing:
        rs = rules.get(rid, {})
        if rs.get("status", "practicing") != "practicing":
            continue
        watching.append(rid)
        demos = int(rs.get("demonstrations", 0))
        if demos > 0:
            masterable.append((rid, demos))
    if masterable:
        rid, demos = max(masterable, key=lambda t: t[1])
        return (f"✓ prompt-coach · clean prompt · closest to mastery: "
                f"{rid} {min(demos, min_demonstrations)}/{min_demonstrations} demonstrated")
    if watching:
        # Name the rules being watched (up to 2) so the signal is actionable
        # — "watching for: no-verify-loop" beats "watching 1 rule".
        shown = ", ".join(watching[:2])
        extra = f" +{len(watching) - 2}" if len(watching) > 2 else ""
        return f"✓ prompt-coach · clean prompt · watching for: {shown}{extra}"
    return "✓ prompt-coach · clean prompt · all active rules mastered 🎓"


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
        if outcome in ("skipped:conversational",
                        "skipped:multi-choice-answer",
                        "skipped:option-list-answer"):
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


def _append_graduation_event(local_dir: Path, rule_id: str, from_status: str,
                              to_status: str, fires_total: int,
                              clean_streak: int, demonstrations: int = 0) -> None:
    """v0.27.0 — append a graduation event line to log.md so users can grep
    `event=graduation` and audit when each rule mastered (or went inactive)
    and how much evidence it had at the time. v0.40.0 adds demonstrations
    (the mastery driver)."""
    log = local_dir / "log.md"
    log.parent.mkdir(parents=True, exist_ok=True)
    date = _today()
    body = log.read_text(encoding="utf-8") if log.exists() else ""
    lines_out = []
    if not log.exists():
        lines_out.append("# prompt-coach log\n")
    header = f"## {date}\n"
    if header.strip() not in body:
        lines_out.append(header)
    lines_out.append(
        f"- [{_now_iso()}] event=graduation rule={rule_id} "
        f"from={from_status} to={to_status} "
        f"demonstrations={demonstrations} "
        f"fires_total={fires_total} clean_streak={clean_streak}"
    )
    with log.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines_out) + "\n")


def _migrate_v27_inactive_status(g: dict, local_dir: Path) -> int:
    """v0.27.0 — auto-migration. Rules that graduated pre-v0.27 with
    fires_total == 0 were labeled `mastered` because the old logic
    ignored evidence. Now they should be `inactive` — same "frees the
    active slot" behavior, but doesn't claim mastery. Idempotent (only
    migrates if a rule is currently `mastered` AND `fires_total == 0`).
    Returns the number of rules migrated so the caller can log it."""
    rules = g.get("rules", {})
    if not isinstance(rules, dict):
        return 0
    migrated = 0
    for rid, rs in rules.items():
        if (rs.get("status") == "mastered"
            and int(rs.get("fires_total", 0)) == 0):
            rs["status"] = "inactive"
            _append_graduation_event(
                local_dir, rid, "mastered", "inactive",
                int(rs.get("fires_total", 0)),
                int(rs.get("clean_streak", 0)),
            )
            migrated += 1
    if migrated > 0:
        # Marker on global state so the migration only logs once per install
        g["v27_migration_done"] = True
    return migrated


def _migrate_v40_demonstrations(g: dict) -> int:
    """v0.40.0 — grandfather migration for demonstration-driven mastery. The
    `demonstrations` counter is new, so pre-v0.40 rules have no history to
    recover. Rather than wipe existing masteries, GRANDFATHER them: backfill
    demonstrations=0 and tag mastered rules `mastery_basis: "legacy"` so the
    mastery dashboard can distinguish earned (demonstration-backed) from
    legacy masteries. Non-destructive + idempotent. Users who want a rule to
    re-earn mastery honestly can `mastery-reset <rule>`."""
    rules = g.get("rules", {})
    if not isinstance(rules, dict) or g.get("v40_migration_done"):
        return 0
    tagged = 0
    for rs in rules.values():
        rs.setdefault("demonstrations", 0)
        if rs.get("status") == "mastered" and "mastery_basis" not in rs:
            rs["mastery_basis"] = "legacy"
            tagged += 1
    g["v40_migration_done"] = True
    return tagged


# ── v0.41.0 — acceptance loop (Proposal 1) ─────────────────────────────────
# The collaborator rewrite is only as good as whether the user TAKES it.
# Copilot's north-star metric is acceptance rate; segmented by suggestion type
# it tells you which rules produce rewrites that land. We record the user's
# next-turn reply (yes/no/edit) per rule. `edited` is a POSITIVE signal (the
# coaching landed, the specifics didn't) — distinct from `rejected`.

_REPLY_ACCEPT = re.compile(
    r"^(y|yes|yep|yeah|ok|okay|sure|proceed|go|go ahead|do it|sounds good|"
    r"lgtm|ship it|please do|yes please)$")
_REPLY_REJECT = re.compile(
    r"^(n|no|nope|nah|original|keep original|as is|leave it|use original)$")


def _classify_reply(prompt: str) -> str | None:
    """Classify a reply to a prior collaborator rewrite. Returns
    'accepted' / 'edited' / 'rejected', or None if it isn't a clear reply
    (a fresh substantive prompt is None — we don't guess at implicit
    rejections, keeping the ledger high-precision)."""
    p = re.sub(r"[.!,\s]+$", "", prompt.strip().lower())
    if _REPLY_ACCEPT.fullmatch(p):
        return "accepted"
    if _REPLY_REJECT.fullmatch(p):
        return "rejected"
    if re.match(r"^edit\b", p):
        return "edited"
    return None


def _record_acceptance(g: dict, l: dict, prompt_raw: str) -> str | None:
    """If a collaborator rewrite was offered last prompt and THIS prompt is a
    clear yes/no/edit reply, record the outcome per rule (and globally).
    Returns the verdict, or None. Idempotent per reply — clears
    last_prompt_fired_rules once recorded so a reply isn't double-counted."""
    offered = list(l.get("last_prompt_fired_rules", []) or [])
    if not offered:
        return None
    verdict = _classify_reply(prompt_raw)
    if verdict is None:
        return None
    for rid in offered:
        rs = g.setdefault("rules", {}).setdefault(rid, {})
        oc = rs.setdefault("outcomes", {"accepted": 0, "edited": 0, "rejected": 0})
        oc[verdict] = int(oc.get(verdict, 0)) + 1
        rs["last_outcome_at"] = _now_iso()
    tally = g.setdefault("acceptance", {"accepted": 0, "edited": 0, "rejected": 0})
    tally[verdict] = int(tally.get(verdict, 0)) + 1
    l["last_prompt_fired_rules"] = []  # consumed
    return verdict


def _rule_precision(rs: dict, min_outcomes: int = 4) -> float | None:
    """Per-rule precision = (accepted + edited) / all recorded outcomes.
    `edited` counts as a hit (the coaching landed). Returns None until at
    least `min_outcomes` outcomes are recorded (too little signal to gate)."""
    oc = rs.get("outcomes") or {}
    a = int(oc.get("accepted", 0)); e = int(oc.get("edited", 0))
    r = int(oc.get("rejected", 0))
    total = a + e + r
    if total < max(1, min_outcomes):
        return None
    return (a + e) / total


# ── v0.41.0 — decaying mastery (Proposal 3) ────────────────────────────────
# Prompting is an accuracy-based cognitive skill, exactly the kind that decays
# with non-use (Arthur 1998; Psych Bulletin 2024 — ~half lost by ~6.5 months).
# So mastery is NOT terminal: a mastered rule carries a review-due timestamp on
# an EXPANDING schedule (spacing effect; Nature Rev Psych 2022). Each natural
# use (a demonstration) is spaced retrieval that resets/extends the clock. If
# the clock lapses with no natural use, the rule decays to a `watch` tier and
# must be freshly re-demonstrated to re-graduate (retrieval-practice loop).

def _parse_iso(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _days_since(iso: str | None) -> float | None:
    """Days elapsed since an ISO timestamp (>0 = in the past). None if unset."""
    dt = _parse_iso(iso) if iso else None
    if dt is None:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0


def _review_intervals(cfg: dict) -> list[int]:
    v = cfg.get("review_intervals_days") or [30, 90, 180]
    try:
        out = [int(x) for x in v if int(x) > 0]
    except (TypeError, ValueError):
        out = []
    return out or [30, 90, 180]


def _set_review_due(gr: dict, cfg: dict, stage: int) -> None:
    """Arm (or re-arm) a mastered rule's review clock at the given expanding
    stage, keyed off wall-clock non-use."""
    intervals = _review_intervals(cfg)
    stage = max(0, min(stage, len(intervals) - 1))
    gr["review_stage"] = stage
    due = datetime.now(timezone.utc) + timedelta(days=intervals[stage])
    gr["review_due_at"] = due.strftime("%Y-%m-%dT%H:%M:%SZ")


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
    # v0.29.0 — master switch. When disabled, do nothing.
    if not bool(cfg.get("enabled", True)):
        return 0
    # v0.29.0 — nudge_style is no longer read; rendering is always inline.
    # Legacy configs may still have `nudge_style: <anything>` set; ignore it.
    # For internal outcome-string compatibility (log-review, stats parse
    # `nudged:<style>:...`), we keep the placeholder "inline" hardcoded.
    cfg["nudge_style"] = "inline"

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

    # v0.27.0 — one-shot auto-migration for legacy "mastered with 0 fires"
    # rules. Runs once per install (marker on global state); each migrated
    # rule is logged as a graduation event so the audit trail is preserved.
    # Safe: idempotent (only touches rules that meet the criteria) and
    # non-destructive (fires_total, clean_streak stay put; only status
    # changes from "mastered" to "inactive").
    if not g.get("v27_migration_done"):
        n_migrated = _migrate_v27_inactive_status(g, local_dir)
        # Marker set inside the helper only if we actually migrated rules;
        # for a fresh install with nothing to migrate, set the marker here
        # so subsequent runs don't scan again.
        g["v27_migration_done"] = True

    # v0.40.0 — grandfather existing masteries into the demonstration model
    # (backfill demonstrations=0, tag mastered rules as legacy). Idempotent.
    _migrate_v40_demonstrations(g)

    # Increment prompt counters.
    g["prompt_count"] = int(g.get("prompt_count", 0)) + 1
    l["prompt_count"] = int(l.get("prompt_count", 0)) + 1

    # v0.13.0 — bug-report phrase: user flagged the PREVIOUS prompt's
    # analysis for review. Append the last non-conversational log entry
    # (which is the analysis being complained about) to candidates.jsonl.
    if is_bug_report_phrase(prompt_raw):
        _flag_previous_for_review(local_dir, prompt_raw)

    # v0.41.0 — acceptance loop (Proposal 1). If a collaborator rewrite was
    # offered last prompt and THIS prompt is a clear yes/no/edit reply,
    # record the per-rule outcome BEFORE the conversational short-circuit
    # (which would otherwise swallow "yes"/"no" and lose the signal).
    _acceptance_verdict = _record_acceptance(g, l, prompt_raw)

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

    # v0.24.0 — transcript-aware picker-answer short-circuit.
    # If the last assistant turn was an AskUserQuestion (definitive) or a
    # `?` followed by a bulleted/numbered list (heuristic — catches
    # prefilled-continuation cases), the user's next prompt is really an
    # answer to that picker, not their fresh authored ask. Any rule the
    # answer text happens to match is a false positive. Never raises;
    # missing/broken transcript resolves to None so the coach continues
    # to analyze prompts normally.
    picker_reason = picker_answer_reason(cwd)
    if picker_reason:
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
            "outcome": f"skipped:{picker_reason}",
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

    threshold = int(cfg.get("graduation_threshold", 15))
    mastery_events: list[str] = []  # rule ids that graduated this prompt
    demoted_events: list[str] = []  # rule ids that lost mastery this prompt

    # v0.40.0 — EARNED MASTERY. Compute which active rules the user actively
    # DEMONSTRATED this prompt: their mirroring positive detector fired. This
    # is the mastery signal (presence of the good technique), independent of
    # whether a nudge also fired on some other rule. Praise is still
    # suppressed on nudged prompts (below); demonstration-counting is not.
    demonstrated_rules: set[str] = set()
    for _pid, _p in POSITIVES_BY_ID.items():
        if _p.mirrors in active:
            try:
                if _p.check(prompt):
                    demonstrated_rules.add(_p.mirrors)
            except Exception:
                pass  # never let a bad regex break the hook

    # Bookkeeping: update every active rule's streak.
    for rid in active:
        gr = g["rules"].setdefault(rid, {
            "status": "practicing",
            "fires_total": 0,
            "clean_streak": 0,
            "demonstrations": 0,
            "last_fired_at": None,
            "last_nudged_at": None,
            "last_demo_at": None,
            "graduated_at": None,
        })
        gr.setdefault("demonstrations", 0)  # v0.40 — backfill on old state
        lr = l["rules"].setdefault(rid, {
            "fires_here": 0,
            "clean_streak_here": 0,
            "last_fired_at": None,
            "last_nudged_at": None,
            "last_nudged_prompt": None,
        })
        gr["status"] = gr.get("status") or "practicing"

        # v0.41.0 (P3) — decay a mastered rule whose review window has lapsed
        # with no natural use down to `watch`. It re-enters active coaching
        # and must be freshly re-demonstrated to re-graduate (retrieval).
        if gr.get("status") == "mastered":
            if not gr.get("review_due_at"):
                # Lazily arm the clock for pre-P3 (grandfathered) masteries so
                # they participate in decay instead of being immortal.
                _set_review_due(gr, cfg, int(gr.get("review_stage", 0)))
            overdue = _days_since(gr.get("review_due_at"))
            if overdue is not None and overdue > 0:
                gr["status"] = "watch"
                gr["watch_base_demos"] = int(gr.get("demonstrations", 0))
                gr["watch_since"] = _now_iso()

        if rid in fired:
            gr["fires_total"] = int(gr.get("fires_total", 0)) + 1
            gr["clean_streak"] = 0
            gr["last_fired_at"] = _now_iso()
            lr["fires_here"] = int(lr.get("fires_here", 0)) + 1
            lr["clean_streak_here"] = 0
            lr["last_fired_at"] = _now_iso()
            # v0.41.0 (P3) — a rule tripped while in `watch` is a real
            # regression: demote to practicing so it must re-earn mastery.
            if gr.get("status") == "watch":
                gr["status"] = "practicing"
                gr.pop("watch_base_demos", None)
        else:
            gr["clean_streak"] = int(gr.get("clean_streak", 0)) + 1
            lr["clean_streak_here"] = int(lr.get("clean_streak_here", 0)) + 1
            # v0.40.0 — count a demonstration when the user actively used the
            # good technique (mirroring positive fired) on a prompt that did
            # NOT trip this rule. This is the evidence mastery is built on.
            if rid in demonstrated_rules:
                gr["demonstrations"] = int(gr.get("demonstrations", 0)) + 1
                gr["last_demo_at"] = _now_iso()
                # v0.41.0 (P3) — natural use of a MASTERED rule is spaced
                # retrieval: reset + expand its review clock (skill refreshed).
                if gr.get("status") == "mastered":
                    _set_review_due(gr, cfg, int(gr.get("review_stage", 0)) + 1)

        # v0.40.0 — EARNED (demonstration-driven) graduation. Mastery is
        # evidence of the *good technique*, not the absence of the mistake:
        #   demonstrations >= min_demonstrations
        #     AND clean_streak >= regression_guard  → "mastered"
        #       (you used the technique enough times AND aren't currently
        #        relapsing)
        #   demonstrations == 0 AND clean_streak >= inactive_after → "inactive"
        #       (the rule never applied to how you prompt — free the active
        #        slot without claiming a mastery you never earned; this also
        #        subsumes the old fires==0 retirement)
        #   else → stay "practicing" (keep watching + counting demos)
        # "mastered" and "inactive" both free the active-rules slot so
        # higher-tier rules can activate; only "mastered" gets refresher
        # fires or counts in stats.
        min_demos = int(cfg.get("min_demonstrations", 3))
        regression_guard = int(cfg.get("regression_guard", 3))
        inactive_after = int(cfg.get("inactive_after", threshold))
        status_now = gr.get("status")
        if rid not in fired and status_now not in ("mastered", "inactive"):
            demos = int(gr.get("demonstrations", 0))
            new_status = None
            if status_now == "watch":
                # v0.41.0 (P3) — re-graduate only on a FRESH demonstration
                # since decay (retrieval practice), not a stale demo count.
                if (demos > int(gr.get("watch_base_demos", 0))
                        and gr["clean_streak"] >= regression_guard):
                    new_status = "mastered"
                    mastery_events.append(rid)
            elif demos >= min_demos and gr["clean_streak"] >= regression_guard:
                new_status = "mastered"
                mastery_events.append(rid)
            elif demos == 0 and gr["clean_streak"] >= inactive_after:
                new_status = "inactive"
                # No mastery event; nothing to praise
            if new_status is not None:
                prior_status = gr.get("status", "practicing")
                gr["status"] = new_status
                gr["graduated_at"] = _now_iso()
                gr["mastery_basis"] = (
                    "demonstrated" if new_status == "mastered" else "unexercised")
                gr["post_mastery_fires"] = 0
                gr["post_mastery_fire_prompts"] = []
                if new_status == "mastered":
                    # v0.41.0 (P3) — arm the review clock. Fresh mastery
                    # starts at stage 0; a re-graduation from watch expands
                    # (the next non-use window is longer).
                    _set_review_due(
                        gr, cfg,
                        (int(gr.get("review_stage", 0)) + 1)
                        if prior_status == "watch" else 0)
                    gr.pop("watch_base_demos", None)
                    gr.pop("watch_since", None)
                # Write a graduation event to the local log so the user can
                # grep `event=graduation` and audit the mastery timeline.
                _append_graduation_event(local_dir, rid, prior_status,
                                          new_status, int(gr.get("fires_total", 0)),
                                          gr["clean_streak"],
                                          demonstrations=demos)

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

    # v0.38.0 — Collaborator is the ONLY mode. When any rule fires, Claude
    # does the analysis + rewrite in the same response (the C+D
    # architecture). The legacy v0.16-v0.28 hand-written emit path (variant
    # picking, disclosure levels, voice presets, LLM-compose, refresher
    # boxes) was removed — the `coach_style: nudge` option is gone.
    #
    # The canonical bookkeeping loop above (over `active`) has ALREADY
    # updated fires_total / clean_streak / graduation / mastery_events for
    # every active rule this prompt. The intercept only builds the
    # additionalContext instruction; it must NOT re-touch state (that was
    # the v0.34 double-count bug). Mastery events still flow to the praise
    # layer below, so the congrats renders here too.
    if fired:
        # v0.41.0 (Proposal 2) — session fatigue cap. The marketing-fatigue
        # bandit result: firing too often makes the signal non-stationary
        # (the user tunes it out). Cap visible rewrites within a rolling
        # window; over the cap we still do all bookkeeping + log the fire,
        # we just don't render the block (silence beats nagging).
        window = int(cfg.get("nudge_window", 20))
        cap = int(cfg.get("max_nudges_per_window", 6))
        recent = [p for p in (g.get("recent_nudge_prompts") or [])
                  if int(g.get("prompt_count", 0)) - int(p) < window]
        if cap > 0 and len(recent) >= cap:
            outcome = f"capped:candidates={len(fired)}"  # silenced by fatigue cap
        else:
            context_line = _v34_context_for_claude(
                prompt_raw, list(fired),
                show_urls=bool(cfg.get("show_source_urls", True)))
            outcome = f"collaborator:candidates={len(fired)}"
            recent.append(int(g.get("prompt_count", 0)))
        g["recent_nudge_prompts"] = recent

    # ---------------- Encouragement layer ---------------- #
    # Only consider praise on prompts that did NOT emit a nudge (Kohn 1993:
    # never dilute a correction with praise on the same prompt). Also skip
    # entirely if paused.
    positive_fires: list[str] = []
    praise_choice = None
    # v0.38.0 — if the collaborator block fired (any rule matched), that
    # counts as "spoke this prompt" for Kohn's don't-dilute-praise
    # principle: no praise on the same prompt.
    nudged_this_prompt = bool(fired) and outcome != "paused"
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
        outcome = f"praised:{kind}:{cfg['nudge_style']}"
        # v0.35.0 — praise had NO inline branch before then, so from v0.29
        # (when rendering was hardcoded to inline) through v0.34 the entire
        # encouragement layer — positive detectors, first-after-fire, AND
        # mastery congrats — was computed then silently dropped. This
        # restores it. Mastery gets a distinct celebratory line; ordinary
        # praise a quieter one. (v0.37.1 — dead both/silent branch + the
        # _praise_box stderr helper removed; rendering is always inline.)
        if kind == "mastery":
            # praise_text already carries the celebration ("🎉 Rule
            # mastered: **X**. That's N clean prompts…"). Prefix the
            # coach glyph, strip a leading 🎉 to avoid a double emoji.
            body = praise_text.lstrip()
            if body.startswith("🎉"):
                body = body[1:].lstrip()
            ack = f"🎓 prompt-coach — {body}"
            context_line = (
                f"[prompt-coach · inline · mastery] The user just graduated "
                f"a rule to mastered — a real milestone. Render EXACTLY this "
                f"ONE line at the very START of your response, verbatim, "
                f"then address their task:\n\n{ack}\n\n"
                f"It's a genuine congratulation; render it warmly but don't "
                f"expand on it or make the user respond to it.")
        elif kind == "first-after-fire":
            p = POSITIVES_BY_ID[pid_or_rid]
            ack = (f"✨ prompt-coach — nice, you applied "
                   f"{p.mirrors} right after the nudge. {praise_text}")
            context_line = (
                f"[prompt-coach · inline · praise] Render EXACTLY this ONE "
                f"line at the very START of your response, verbatim, then "
                f"address the task:\n\n{ack}\n\n"
                f"Keep it to that line; it's light encouragement, not a topic.")
        else:
            ack = f"✨ prompt-coach — {praise_text}"
            context_line = (
                f"[prompt-coach · inline · praise] Render EXACTLY this ONE "
                f"line at the very START of your response, verbatim, then "
                f"address the task:\n\n{ack}\n\n"
                f"Keep it to that line; it's light encouragement, not a topic.")

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

    # v0.28.0 — proactive tips. Two firing modes:
    #   Mode B (graduation-unlock): rule masters → fire paired tip on same
    #     turn (learning-sequence scaffolding). Priority over Mode A.
    #   Mode A (matching): heuristic on prompt + cooldown + variable-ratio.
    #     Only if nothing else fired (nudge/refresher/praise) so the coach
    #     doesn't stack advice.
    fired_tip_id: str | None = None
    fired_tip_mode: str | None = None
    if cfg.get("tips_enabled", True):
        # Mode B: paired to a mastery event that happened this turn
        for mastered_rid in mastery_events:
            paired = _TIP_ON_MASTERY.get(mastered_rid)
            if paired and paired in TIPS_BY_ID:
                fired_tip_id = paired
                fired_tip_mode = "graduation-unlock"
                break
        # Mode A: on-topic heuristic — only if nothing above emitted anything
        if fired_tip_id is None and outcome == "no-emit" and not nudged_this_prompt:
            candidate = _pick_matching_tip(prompt, cfg, g)
            if candidate:
                fired_tip_id = candidate
                fired_tip_mode = "match"

    if fired_tip_id:
        tip = TIPS_BY_ID[fired_tip_id]
        _record_tip_fire(g, fired_tip_id)
        # If a rule already emitted (nudge / praise), don't overwrite the
        # outcome — record the tip as an additional log field. But if
        # outcome is "no-emit", promote to tipped:inline:<tip-id>.
        if outcome == "no-emit":
            outcome = f"tipped:inline:{fired_tip_id}:{fired_tip_mode}"
        # Render tip inline (v0.37.1 — dead both/silent branches removed).
        bar = "━" * 60
        tip_box = (
            f"{bar}\n"
            f"💡 prompt-coach tip — {fired_tip_id}: {tip.technique}\n\n"
            f"{tip.body}\n"
            f"{bar}"
        )
        if context_line is None:
            context_line = (
                f"[prompt-coach · inline · tip] Render the following block "
                f"AT THE VERY START of your response, VERBATIM, before "
                f"addressing the user's task:\n\n{tip_box}\n\n"
                f"Then answer the user's actual question. Guidance for the "
                f"response: {tip.guidance}"
            )

    # ---------------- Liveness acknowledgment (v0.35.0) ---------------- #
    # The coach was "too silent": since v0.29 it only spoke on rule hits, so
    # a clean prompt got nothing and the user couldn't tell it was alive.
    # `ack_clean` (default on) emits a compact, ambient one-liner on a clean
    # prompt confirming the coach ran + showing mastery progress.
    #
    # This is deliberately NOT praise. Praise is evaluative and must stay
    # sparing (Kohn 1993; Deci & Ryan 2000 on controlling vs informational
    # feedback). The ack is *informational* — a heartbeat, like a test
    # runner's green dot or a shell's git-branch segment. Informational
    # progress feedback supports competence without the wear-out that
    # repeated praise causes, and surfacing "N/threshold to mastery"
    # leverages the endowed-progress effect (Nunes & Drèze 2006). It uses a
    # distinct glyph (✓) from nudge (🎯) / refresher (🔄) / tip (💡) /
    # praise (✨🎓) so it reads as status, not an alert (Sasse & Rashid 2013
    # on keeping informational status off the alert channel).
    #
    # Priority: it fires ONLY when nothing else spoke this prompt
    # (outcome == "no-emit", context_line is None) and no rule fired. So
    # nudge > refresher > praise > tip > ack. Rate-controlled by `ack_ratio`
    # (default 1 = every clean prompt; raise to dial the heartbeat down).
    if (cfg.get("ack_clean", True)
            and context_line is None
            and outcome == "no-emit"
            and not fired
            and not is_paused):
        ack_ratio = max(1, int(cfg.get("ack_ratio", 1)))
        since = int(g.get("acks_since", 0)) + 1
        if since >= ack_ratio:
            g["acks_since"] = 0
            ack_line = _ack_line(g, active_practicing, threshold,
                                 int(cfg.get("min_demonstrations", 3)),
                                 demonstrated=sorted(demonstrated_rules))
            outcome = "ack:clean"
            context_line = (
                f"[prompt-coach · inline · ack] The user's prompt was clean — "
                f"no rules fired. Render EXACTLY this ONE line at the very "
                f"start of your response, verbatim, then answer normally:\n\n"
                f"{ack_line}\n\n"
                f"Keep it to that single line — it's an ambient liveness "
                f"signal, not a topic. Don't comment on it or invite a reply.")
        else:
            g["acks_since"] = since

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
        "chosen": (fired[0] if fired else None),
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
