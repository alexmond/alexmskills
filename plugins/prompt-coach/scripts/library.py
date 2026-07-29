"""Local task-matching over Anthropic's Claude Code Prompt Library snapshot.

Zero-dependency, deterministic keyword/tag matcher (no embeddings, no network,
no LLM) — cheap enough to call from the UserPromptSubmit hook. Reads the JSON
snapshot produced by gen-prompt-library.py and returns the closest gold-standard
template(s) for a user's prompt, so the coach can ground a rewrite or answer a
"show me a prompt for X" lookup.

The library prompts are Anthropic documentation content (see the snapshot's
`note`), vendored with attribution for offline matching.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DATA = _HERE.parent / "data" / "prompt-library.json"

# Intent keywords per category — a category hit is a strong signal that the
# user's task shape matches that family of library prompts.
CAT_KEYWORDS = {
    "Review": ["review", "audit", "critique", "look over", "flag anything"],
    "Test": ["test", "tests", "coverage", "tdd", "unit test"],
    "Debug": ["debug", "fix", "failing", "broken", "why is", "why does", "root cause"],
    "Refactor": ["refactor", "migrate", "port", "rename", "restructure", "extract"],
    "Understand": ["explain", "understand", "how does", "what does", "overview",
                   "trace", "where do", "walk me through"],
    "Implement": ["implement", "add", "build", "create", "write a", "feature", "endpoint"],
    "Plan": ["plan", "scope", "spec", "break down", "break this down", "roadmap"],
    "Prototype": ["prototype", "mockup", "kanban", "drag-and-drop", "quick ui"],
    "Automate": ["hook", "automate", "github actions", "ci", "pipeline", "pre-commit"],
    "Release": ["release", "deploy", "ship", "changelog", "version bump", "tag"],
    "Incident": ["incident", "outage", "postmortem", "rollback", "alert", "on-call"],
    "Git": ["commit", "merge conflict", "rebase", "branch", "open a pr", "pull request"],
    "Data": ["query", "sql", "logs", "metrics", "dashboard", "report on"],
    "Steer": ["try again", "too much", "keep only", "backward-compatible", "that is not"],
    "Onboard": ["onboard", "get oriented", "overview of this codebase", "new to this"],
}

_STOP = set(
    "the a an of to in on for and or but with your my our this that these those it its "
    "is are be do does can could should would you i we me us as at by from into out up "
    "then so if not no yes all any each every some what how why where when which".split()
)


def _tok(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9][a-z0-9+.-]*", s.lower())
            if w not in _STOP and len(w) > 2}


@lru_cache(maxsize=1)
def load() -> dict:
    if not _DATA.exists():
        return {"entries": [], "count": 0}
    return json.loads(_DATA.read_text())


def fill(entry: dict) -> str:
    """The prompt with its {slot} placeholders substituted by their defaults."""
    p = entry.get("prompt", "")
    for k, v in (entry.get("slots") or {}).items():
        p = p.replace("{" + k + "}", v)
    return p


def score_entry(prompt_tokens: set[str], prompt_lower: str, entry: dict) -> float:
    """Task-shape closeness: token overlap (weighted) + a category-keyword boost
    + a Jaccard tiebreak. Deterministic; higher is closer."""
    et = _tok(entry.get("prompt", "") + " " + entry.get("cat", ""))
    overlap = len(prompt_tokens & et)
    cat_hit = any(kw in prompt_lower for kw in CAT_KEYWORDS.get(entry.get("cat", ""), []))
    if not overlap and not cat_hit:
        return 0.0
    score = 2.0 * overlap + (3.0 if cat_hit else 0.0)
    union = len(prompt_tokens | et) or 1
    return score + overlap / union


def match(prompt: str, k: int = 3, min_score: float = 1.0) -> list[dict]:
    """Top-k library entries closest to `prompt`, each annotated with `_score`
    and `_filled` (slots substituted). Empty if nothing clears `min_score`."""
    entries = load().get("entries", [])
    if not entries:
        return []
    pt, pl = _tok(prompt), prompt.lower()
    scored = []
    for e in entries:
        s = score_entry(pt, pl, e)
        if s >= min_score:
            scored.append((s, e))
    scored.sort(key=lambda x: (-x[0], x[1].get("id", "")))
    out = []
    for s, e in scored[:k]:
        d = dict(e)
        d["_score"] = round(s, 2)
        d["_filled"] = fill(e)
        out.append(d)
    return out


def best(prompt: str, min_score: float = 3.0) -> dict | None:
    """Single best match at a confidence floor — for rewrite grounding, where a
    weak match is worse than none. `min_score` >= 3.0 requires a category hit."""
    m = match(prompt, k=1, min_score=min_score)
    return m[0] if m else None


def by_category(cat: str) -> list[dict]:
    """All templates in a library category (case-insensitive), each with slots
    filled. Used by the roles system to anchor a persona in its canonical
    prompt shapes (e.g. the `reviewer` role → the 'Review' templates)."""
    cl = (cat or "").lower()
    out = []
    for e in load().get("entries", []):
        if (e.get("cat", "").lower() == cl):
            d = dict(e)
            d["_filled"] = fill(e)
            out.append(d)
    return out


def by_role(role: str) -> list[dict]:
    """All templates tagged with an org role (pm / design / security / ops /
    docs / data / marketing), each with slots filled."""
    rl = (role or "").lower()
    out = []
    for e in load().get("entries", []):
        if rl in [r.lower() for r in e.get("roles", [])]:
            d = dict(e)
            d["_filled"] = fill(e)
            out.append(d)
    return out
