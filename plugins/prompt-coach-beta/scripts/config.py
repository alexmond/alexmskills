#!/usr/bin/env python3
"""prompt-coach-beta v0.18+ — /prompt-coach-beta:config helper.

Reads CONFIG_SCHEMA + DEFAULT_CONFIG from the sibling analyze-prompt.py and
implements the verbs used by the config slash command:

    show [category]     categorized dashboard (or one category)
    get <key>           print resolved value only
    describe <key>      metadata + description
    set <key> <value>   validate + write to scoped config
    reset <key>         remove key from scoped config
    reset-all           wipe the scoped config file
    diff                only keys where the resolved value != default
    export              print resolved config as JSON

Flags:
    --scope global (default) | repo
    --dry-run            on set/reset: show what would change without writing
    --cwd <path>         override working dir (for repo-scoped config)
    --json               machine-readable output (used by tests)

All writes preserve keys the schema doesn't know about (deep-merge, no truncation).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import textwrap
from pathlib import Path

# ── Locate + import the sibling analyzer for CONFIG_SCHEMA/DEFAULT_CONFIG ────

_HERE = Path(__file__).resolve().parent
_ANALYZER_PATH = _HERE / "analyze-prompt.py"
_spec = importlib.util.spec_from_file_location("_prompt_coach_analyzer",
                                                _ANALYZER_PATH)
_analyzer = importlib.util.module_from_spec(_spec)
# Register BEFORE exec so @dataclass decorators can resolve their module.
sys.modules["_prompt_coach_analyzer"] = _analyzer
_spec.loader.exec_module(_analyzer)

CONFIG_SCHEMA = _analyzer.CONFIG_SCHEMA
DEFAULT_CONFIG = _analyzer.DEFAULT_CONFIG
RULES = _analyzer.RULES
config_key_source = _analyzer.config_key_source
config_categories = _analyzer.config_categories
config_keys_in_category = _analyzer.config_keys_in_category


# ── Config file paths ──────────────────────────────────────────────────────

def _global_config_path() -> Path:
    return Path.home() / ".claude" / "prompt-coach" / "config.json"


def _repo_config_path(cwd: Path) -> Path:
    return cwd / ".claude" / "prompt-coach" / "config.json"


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def _scope_path(scope: str, cwd: Path) -> Path:
    return _global_config_path() if scope == "global" else _repo_config_path(cwd)


def _resolve(cwd: Path) -> tuple[dict, dict, dict]:
    """Return (default, global_overrides, repo_overrides)."""
    gcfg = _load_json(_global_config_path())
    rcfg = _load_json(_repo_config_path(cwd))
    return DEFAULT_CONFIG, gcfg, rcfg


def _resolved_value(key: str, cwd: Path):
    """Layer resolution: repo → global → default."""
    _, gcfg, rcfg = _resolve(cwd)
    if key in rcfg:
        return rcfg[key]
    if key in gcfg:
        return gcfg[key]
    return DEFAULT_CONFIG.get(key)


# ── Value coercion / validation ────────────────────────────────────────────

def _coerce(key: str, raw: str):
    """Convert CLI string → typed value per schema. Raises ValueError on bad input."""
    if key not in CONFIG_SCHEMA:
        raise ValueError(f"unknown key: {key}")
    entry = CONFIG_SCHEMA[key]
    t = entry["type"]
    if t == "str":
        val = raw
        if "choices" in entry and val not in entry["choices"]:
            raise ValueError(
                f"'{val}' is not one of {entry['choices']} for {key}")
        return val
    if t == "int":
        try:
            return int(raw)
        except ValueError:
            raise ValueError(f"expected int for {key}, got '{raw}'")
    if t == "bool":
        low = raw.strip().lower()
        if low in ("true", "1", "yes", "on"):
            return True
        if low in ("false", "0", "no", "off"):
            return False
        raise ValueError(f"expected bool for {key}, got '{raw}'")
    if t == "list[str]":
        # Accept either JSON array or comma-separated
        raw = raw.strip()
        if raw.startswith("["):
            v = json.loads(raw)
        else:
            v = [s.strip() for s in raw.split(",") if s.strip()]
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise ValueError(f"expected list[str] for {key}, got '{raw}'")
        return v
    if t == "obj":
        v = json.loads(raw)
        if not isinstance(v, dict):
            raise ValueError(f"expected object for {key}, got '{raw}'")
        return v
    raise ValueError(f"unknown schema type '{t}' for {key}")


# ── Rendering ───────────────────────────────────────────────────────────────

_BAR = "─" * 70


def _fmt_value(v) -> str:
    if isinstance(v, list) and not v:
        return "[]"
    if isinstance(v, dict):
        return json.dumps(v, separators=(",", ":"))
    return json.dumps(v) if isinstance(v, str) else str(v)


def cmd_show(cwd: Path, category_filter: str | None = None,
             as_json: bool = False) -> int:
    _, gcfg, rcfg = _resolve(cwd)

    if as_json:
        out = {}
        for cat in config_categories():
            if category_filter and cat != category_filter:
                continue
            for k in config_keys_in_category(cat):
                entry = CONFIG_SCHEMA[k]
                out[k] = {
                    "category": cat,
                    "type": entry["type"],
                    "value": _resolved_value(k, cwd),
                    "default": DEFAULT_CONFIG.get(k),
                    "source": config_key_source(k, gcfg, rcfg),
                    "since": entry.get("since"),
                }
        print(json.dumps(out, indent=2))
        return 0

    if category_filter and category_filter not in config_categories():
        print(f"unknown category: {category_filter}", file=sys.stderr)
        print(f"known: {', '.join(config_categories())}", file=sys.stderr)
        return 2

    print(f"prompt-coach-beta — resolved config (default → global → repo)")
    print(f"  global: {_global_config_path()} {'(present)' if _global_config_path().exists() else '(none)'}")
    print(f"  repo:   {_repo_config_path(cwd)} {'(present)' if _repo_config_path(cwd).exists() else '(none)'}")
    print()

    for cat in config_categories():
        if category_filter and cat != category_filter:
            continue
        keys = config_keys_in_category(cat)
        print(f"── {cat} " + "─" * (68 - len(cat)))
        for k in keys:
            val = _resolved_value(k, cwd)
            src = config_key_source(k, gcfg, rcfg)
            entry = CONFIG_SCHEMA[k]
            src_tag = f"[{src}]" if src != "default" else "        "
            print(f"  {k:28s} {_fmt_value(val):20s} {src_tag}  ({entry['type']})")
        print()

    print("Verbs: describe <key> · set <key> <value> · reset <key> · diff · export")
    print("Flags: --scope global|repo · --dry-run")
    return 0


def cmd_get(cwd: Path, key: str, as_json: bool = False) -> int:
    if key not in CONFIG_SCHEMA:
        print(f"unknown key: {key}", file=sys.stderr)
        return 2
    val = _resolved_value(key, cwd)
    if as_json:
        print(json.dumps({key: val, "source": config_key_source(
            key, *_resolve(cwd)[1:])}))
    else:
        print(_fmt_value(val))
    return 0


def cmd_describe(cwd: Path, key: str, as_json: bool = False) -> int:
    if key not in CONFIG_SCHEMA:
        print(f"unknown key: {key}", file=sys.stderr)
        return 2
    entry = CONFIG_SCHEMA[key]
    _, gcfg, rcfg = _resolve(cwd)
    body = {
        "key": key,
        "category": entry["category"],
        "type": entry["type"],
        "default": DEFAULT_CONFIG.get(key),
        "current": _resolved_value(key, cwd),
        "source": config_key_source(key, gcfg, rcfg),
        "choices": entry.get("choices"),
        "example": entry.get("example"),
        "since": entry.get("since"),
        "description": entry["description"],
    }
    if as_json:
        print(json.dumps(body, indent=2))
    else:
        print(f"── {key} " + "─" * (68 - len(key)))
        print(f"  category:    {body['category']}")
        print(f"  type:        {body['type']}")
        if body["choices"]:
            print(f"  choices:     {body['choices']}")
        print(f"  default:     {_fmt_value(body['default'])}")
        print(f"  current:     {_fmt_value(body['current'])}  [{body['source']}]")
        if body["example"] is not None:
            print(f"  example:     {_fmt_value(body['example'])}")
        print(f"  since:       {body['since']}")
        print()
        print("  " + body["description"])
        print()
        print(f"  Set with:   /prompt-coach-beta:config set {key} <value>")
        print(f"  Reset with: /prompt-coach-beta:config reset {key}")
    return 0


def cmd_set(cwd: Path, key: str, raw_value: str, scope: str,
            dry_run: bool = False) -> int:
    if key not in CONFIG_SCHEMA:
        print(f"unknown key: {key}", file=sys.stderr)
        return 2
    try:
        value = _coerce(key, raw_value)
    except ValueError as e:
        print(f"invalid value: {e}", file=sys.stderr)
        return 2

    path = _scope_path(scope, cwd)
    existing = _load_json(path)
    previous = existing.get(key, "<unset>")

    if dry_run:
        print(f"[dry-run] would set {key} = {_fmt_value(value)} in {scope} "
              f"({path})")
        print(f"  previous ({scope}): {_fmt_value(previous) if previous != '<unset>' else '<unset>'}")
        return 0

    merged = dict(existing)
    merged[key] = value
    _save_json(path, merged)
    print(f"set {key} = {_fmt_value(value)} in {scope} config ({path})")
    if previous != "<unset>":
        print(f"  was: {_fmt_value(previous)}")
    resolved = _resolved_value(key, cwd)
    print(f"  resolved: {_fmt_value(resolved)}")
    return 0


def cmd_reset(cwd: Path, key: str, scope: str, dry_run: bool = False) -> int:
    if key not in CONFIG_SCHEMA:
        print(f"unknown key: {key}", file=sys.stderr)
        return 2
    path = _scope_path(scope, cwd)
    existing = _load_json(path)
    if key not in existing:
        print(f"nothing to reset — {key} is not overridden in {scope} config")
        return 0
    previous = existing[key]
    if dry_run:
        print(f"[dry-run] would remove {key} (was {_fmt_value(previous)}) "
              f"from {scope} ({path})")
        return 0
    del existing[key]
    _save_json(path, existing)
    print(f"reset {key} in {scope} config (removed override {_fmt_value(previous)})")
    resolved = _resolved_value(key, cwd)
    print(f"  now resolves to: {_fmt_value(resolved)}")
    return 0


def cmd_reset_all(cwd: Path, scope: str, dry_run: bool = False) -> int:
    path = _scope_path(scope, cwd)
    if not path.exists():
        print(f"nothing to reset — {scope} config does not exist ({path})")
        return 0
    existing = _load_json(path)
    if dry_run:
        print(f"[dry-run] would wipe {scope} config ({path})")
        print(f"  {len(existing)} key(s) would be removed:")
        for k in sorted(existing):
            print(f"    {k} = {_fmt_value(existing[k])}")
        return 0
    path.unlink()
    print(f"wiped {scope} config ({path}) — {len(existing)} key(s) removed")
    return 0


def cmd_diff(cwd: Path, as_json: bool = False) -> int:
    _, gcfg, rcfg = _resolve(cwd)
    diffs = {}
    for k in CONFIG_SCHEMA:
        resolved = _resolved_value(k, cwd)
        default = DEFAULT_CONFIG.get(k)
        if resolved != default:
            diffs[k] = {
                "resolved": resolved,
                "default": default,
                "source": config_key_source(k, gcfg, rcfg),
            }
    if as_json:
        print(json.dumps(diffs, indent=2))
        return 0
    if not diffs:
        print("no overrides — resolved config matches defaults")
        return 0
    print(f"{len(diffs)} override(s):")
    for k, d in diffs.items():
        print(f"  {k:28s} {_fmt_value(d['resolved']):20s} "
              f"(default: {_fmt_value(d['default'])}, source: {d['source']})")
    return 0


def cmd_export(cwd: Path, as_json: bool = True) -> int:
    resolved = {k: _resolved_value(k, cwd) for k in CONFIG_SCHEMA}
    print(json.dumps(resolved, indent=2))
    return 0


# ── v0.19.0: options + mastery ──────────────────────────────────────────────

def cmd_options(cwd: Path, key: str, as_json: bool = False) -> int:
    """v0.19.0 — enumerate the legal values for a key with per-choice
    explanations. For enums: one line per choice with its description.
    For int/bool/list/obj: current + default + example + description."""
    if key not in CONFIG_SCHEMA:
        print(f"unknown key: {key}", file=sys.stderr)
        return 2
    entry = CONFIG_SCHEMA[key]
    current = _resolved_value(key, cwd)
    default = DEFAULT_CONFIG.get(key)
    _, gcfg, rcfg = _resolve(cwd)
    source = config_key_source(key, gcfg, rcfg)
    choices = entry.get("choices")
    choice_descriptions = entry.get("choice_descriptions", {})

    if as_json:
        body = {
            "key": key,
            "type": entry["type"],
            "current": current,
            "default": default,
            "source": source,
        }
        if choices:
            body["options"] = [
                {
                    "value": c,
                    "description": choice_descriptions.get(c, ""),
                    "is_current": c == current,
                    "is_default": c == default,
                }
                for c in choices
            ]
        else:
            body["example"] = entry.get("example")
            body["description"] = entry["description"]
        print(json.dumps(body, indent=2))
        return 0

    print(f"── options for {key} " + "─" * max(4, 60 - len(key)))
    print(f"  type:      {entry['type']}")
    print(f"  current:   {_fmt_value(current)}  [{source}]")
    print(f"  default:   {_fmt_value(default)}")
    print()
    if choices:
        for c in choices:
            marker = ""
            if c == current: marker += " ← current"
            if c == default and c != current: marker += " (default)"
            elif c == default and c == current: marker = " ← current (default)"
            print(f"  * {c}{marker}")
            desc = choice_descriptions.get(c)
            if desc:
                # textwrap handles short tokens correctly (my ad-hoc wrapper
                # in v0.19 glued "+context" and "anti-disagreementguardrails"
                # because a solo short token was concatenated without space).
                for line in textwrap.wrap(desc, width=74,
                                          initial_indent="    ",
                                          subsequent_indent="    "):
                    print(line)
            print()
        print(f"  Set with: /prompt-coach-beta:config set {key} <value>")
        print(f"  Reset:    /prompt-coach-beta:config reset {key}")
    else:
        if entry.get("example") is not None:
            print(f"  example:   {_fmt_value(entry['example'])}")
        print()
        print(f"  {entry['description']}")
        print()
        print(f"  Set with: /prompt-coach-beta:config set {key} <value>")
        print(f"  Reset:    /prompt-coach-beta:config reset {key}")
    return 0


def _global_state_path() -> Path:
    return Path.home() / ".claude" / "prompt-coach" / "state.json"


def _rule_ids_by_tier() -> dict[int, list[str]]:
    """Group all shipped rule ids by tier from the RULES list."""
    out: dict[int, list[str]] = {}
    for r in RULES:
        out.setdefault(r.tier, []).append(r.id)
    return out


def _rule_id_set() -> set[str]:
    return {r.id for r in RULES}


def _mastery_snapshot() -> dict:
    """Read global state.json and classify every shipped rule."""
    state = _load_json(_global_state_path())
    rules_state = state.get("rules", {}) if isinstance(state, dict) else {}
    prompt_count = state.get("prompt_count", 0) if isinstance(state, dict) else 0

    mastered, in_progress, dormant = [], [], []
    for rule in RULES:
        rs = rules_state.get(rule.id, {}) or {}
        status = rs.get("status", "practicing")
        fires_total = int(rs.get("fires_total", 0))
        clean_streak = int(rs.get("clean_streak", 0))
        mastered_at = rs.get("mastered_at")
        item = {
            "id": rule.id,
            "tier": rule.tier,
            "name": rule.name,
            "fires_total": fires_total,
            "clean_streak": clean_streak,
            "status": status,
            "mastered_at": mastered_at,
        }
        if status == "mastered":
            mastered.append(item)
        elif fires_total > 0 or clean_streak > 0:
            in_progress.append(item)
        else:
            dormant.append(item)
    return {
        "prompt_count": prompt_count,
        "mastered": mastered,
        "in_progress": in_progress,
        "dormant": dormant,
        "totals": {
            "mastered": len(mastered),
            "in_progress": len(in_progress),
            "dormant": len(dormant),
            "all": len(RULES),
        },
    }


def cmd_mastery(cwd: Path, as_json: bool = False) -> int:
    """v0.19.0 — mastery dashboard: mastered / in-progress / dormant counts,
    with per-rule details for the first two groups."""
    snap = _mastery_snapshot()
    if as_json:
        print(json.dumps(snap, indent=2))
        return 0

    t = snap["totals"]
    print(f"prompt-coach-beta — mastery snapshot")
    print(f"  Global state:  {_global_state_path()} "
          f"{'(present)' if _global_state_path().exists() else '(none — no fires yet)'}")
    print(f"  Total prompts analyzed: {snap['prompt_count']}")
    print(f"  Rules: {t['mastered']} mastered · {t['in_progress']} in progress · "
          f"{t['dormant']} dormant / {t['all']} shipped")
    print()

    if snap["mastered"]:
        print("── mastered ─────────────────────────────────────────────")
        for r in sorted(snap["mastered"], key=lambda x: (x["tier"], x["id"])):
            date = r["mastered_at"] or "unknown date"
            print(f"  ✓ L{r['tier']}  {r['id']:32s}  "
                  f"fires_total={r['fires_total']:<3d} mastered {date}")
        print()

    if snap["in_progress"]:
        print("── in progress (fires > 0, not yet mastered) ────────────")
        # Sort by clean_streak descending to surface the closest-to-mastery first
        for r in sorted(snap["in_progress"],
                        key=lambda x: (-x["clean_streak"], x["tier"], x["id"])):
            print(f"  · L{r['tier']}  {r['id']:32s}  "
                  f"fires_total={r['fires_total']:<3d} "
                  f"clean_streak={r['clean_streak']:<3d}")
        print()

    if snap["dormant"]:
        # List by tier count, don't enumerate 20+ ids
        by_tier: dict[int, int] = {}
        for r in snap["dormant"]:
            by_tier[r["tier"]] = by_tier.get(r["tier"], 0) + 1
        print(f"── dormant ({t['dormant']} rules never fired) ──────────")
        for tier in sorted(by_tier):
            print(f"     L{tier}: {by_tier[tier]} rule(s)")
        print()

    print("Reset one rule:    /prompt-coach-beta:config mastery-reset <rule-id>")
    print("Reset everything:  /prompt-coach-beta:config mastery-reset-all")
    return 0


def _reset_rule_state(state: dict, rule_id: str) -> dict:
    """Zero fires_total, clean_streak, status, mastered_at for one rule."""
    rules = state.setdefault("rules", {})
    prev = rules.get(rule_id, {}).copy()
    rules[rule_id] = {
        "fires_total": 0,
        "clean_streak": 0,
        "status": "practicing",
        "mastered_at": None,
        # Preserve any coach-internal fields the schema doesn't know about,
        # except the ones we explicitly reset.
        **{k: v for k, v in rules.get(rule_id, {}).items()
           if k not in ("fires_total", "clean_streak", "status",
                        "mastered_at", "recent_variants",
                        "recent_fire_prompts", "silence_until_prompt")},
    }
    return prev


def cmd_mastery_reset(cwd: Path, rule_id: str, dry_run: bool = False) -> int:
    """v0.19.0 — reset a single rule's mastery + fires + streak state."""
    if rule_id not in _rule_id_set():
        print(f"unknown rule id: {rule_id}", file=sys.stderr)
        print(f"  {len(RULES)} rules shipped. Run "
              "`/prompt-coach-beta:config mastery` to see all ids.",
              file=sys.stderr)
        return 2
    state_path = _global_state_path()
    if not state_path.exists():
        print(f"no state file yet ({state_path}) — nothing to reset")
        return 0
    state = _load_json(state_path)
    rules = state.get("rules", {}) if isinstance(state, dict) else {}
    current = rules.get(rule_id, {})
    if not current or (current.get("fires_total", 0) == 0
                       and current.get("clean_streak", 0) == 0
                       and current.get("status", "practicing") == "practicing"):
        print(f"nothing to reset — {rule_id} has no accumulated state")
        return 0
    if dry_run:
        print(f"[dry-run] would reset {rule_id}:")
        print(f"  fires_total: {current.get('fires_total', 0)} → 0")
        print(f"  clean_streak: {current.get('clean_streak', 0)} → 0")
        print(f"  status: {current.get('status', 'practicing')} → practicing")
        if current.get("mastered_at"):
            print(f"  mastered_at: {current.get('mastered_at')} → null")
        return 0
    _reset_rule_state(state, rule_id)
    _save_json(state_path, state)
    print(f"reset {rule_id} — fires_total=0, clean_streak=0, status=practicing")
    return 0


_ANTHROPIC_BASE_URL = ("https://platform.claude.com/docs/en/build-with-claude/"
                       "prompt-engineering/claude-prompting-best-practices")


def cmd_sources(cwd: Path, rule_id: str | None = None,
                as_json: bool = False) -> int:
    """v0.20.0 — surface the citation trail for a rule (or the full mapping).
    Shows every source cited by the rule + the canonical Anthropic-guide
    section slug (if any) with its URL — enables 'why does this rule exist?'
    trace back to authoritative material."""
    # No arg: summary — list every rule with its anthropic_ref
    if rule_id is None:
        rules_by_ref: dict[str | None, list[str]] = {}
        for rule in RULES:
            rules_by_ref.setdefault(rule.anthropic_ref, []).append(rule.id)
        if as_json:
            out = {
                "linked": {ref: rules
                            for ref, rules in rules_by_ref.items() if ref},
                "unlinked": rules_by_ref.get(None, []),
                "anthropic_base_url": _ANTHROPIC_BASE_URL,
            }
            print(json.dumps(out, indent=2))
            return 0
        linked_count = sum(1 for r in RULES if r.anthropic_ref)
        total = len(RULES)
        print(f"prompt-coach-beta — sources mapping ({linked_count}/{total} "
              f"rules link to an Anthropic-guide section)")
        print(f"  Anthropic guide: {_ANTHROPIC_BASE_URL}")
        print()
        for ref in sorted(k for k in rules_by_ref if k is not None):
            print(f"── {ref} " + "─" * max(4, 60 - len(ref)))
            for rid in sorted(rules_by_ref[ref]):
                print(f"  · {rid}")
            print()
        unlinked = rules_by_ref.get(None, [])
        if unlinked:
            print(f"── no Anthropic-guide mapping ({len(unlinked)} rules) "
                  + "─" * max(4, 40 - len(str(len(unlinked)))))
            print("  (Claude-Code-specific rules or novel coach concepts)")
            for rid in sorted(unlinked):
                print(f"  · {rid}")
            print()
        print("Per-rule detail: /prompt-coach-beta:config sources <rule-id>")
        return 0

    # Single-rule detail
    rule = next((r for r in RULES if r.id == rule_id), None)
    if rule is None:
        print(f"unknown rule id: {rule_id}", file=sys.stderr)
        print(f"  Run `/prompt-coach-beta:config sources` for the full list.",
              file=sys.stderr)
        return 2

    if as_json:
        out = {
            "id": rule.id,
            "tier": rule.tier,
            "name": rule.name,
            "anthropic_ref": rule.anthropic_ref,
            "anthropic_url": (f"{_ANTHROPIC_BASE_URL}#{rule.anthropic_ref}"
                              if rule.anthropic_ref else None),
            "sources": [{"title": t, "url": u} for t, u in rule.sources],
        }
        print(json.dumps(out, indent=2))
        return 0

    print(f"── sources for {rule.id} " + "─" * max(4, 55 - len(rule.id)))
    print(f"  tier:  L{rule.tier}")
    print(f"  name:  {rule.name}")
    print()
    if rule.anthropic_ref:
        print(f"  Anthropic guide (canonical upstream):")
        print(f"    section: {rule.anthropic_ref}")
        print(f"    url:     {_ANTHROPIC_BASE_URL}#{rule.anthropic_ref}")
    else:
        print(f"  Anthropic guide: (no direct mapping — coach-specific or "
              f"Claude-Code tool-native)")
    print()
    print(f"  Cited sources ({len(rule.sources)}):")
    for title, url in rule.sources:
        print(f"    · {title}")
        print(f"      {url}")
    return 0


def cmd_mastery_reset_all(cwd: Path, dry_run: bool = False) -> int:
    """v0.19.0 — reset EVERY rule's mastery + streak. Preserves prompt_count
    and any non-rule top-level state (like anti-habituation window state)."""
    state_path = _global_state_path()
    if not state_path.exists():
        print(f"no state file yet ({state_path}) — nothing to reset")
        return 0
    state = _load_json(state_path)
    rules = state.get("rules", {}) if isinstance(state, dict) else {}
    non_default = [rid for rid, rs in rules.items()
                   if rs.get("fires_total", 0) > 0
                   or rs.get("clean_streak", 0) > 0
                   or rs.get("status", "practicing") != "practicing"]
    if not non_default:
        print("nothing to reset — no rule has accumulated state")
        return 0
    if dry_run:
        print(f"[dry-run] would reset {len(non_default)} rule(s):")
        for rid in non_default:
            rs = rules[rid]
            summary = (f"fires={rs.get('fires_total', 0)} "
                       f"streak={rs.get('clean_streak', 0)} "
                       f"status={rs.get('status', 'practicing')}")
            print(f"  {rid:32s} {summary}")
        print()
        print("  prompt_count and other non-rule state will be preserved.")
        return 0
    for rid in non_default:
        _reset_rule_state(state, rid)
    _save_json(state_path, state)
    print(f"reset {len(non_default)} rule(s) — all mastery + streak state cleared")
    print(f"  prompt_count preserved: {state.get('prompt_count', 0)}")
    return 0


# ── CLI ─────────────────────────────────────────────────────────────────────

def _main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="config", description=__doc__)
    p.add_argument("--scope", choices=["global", "repo"], default="global")
    p.add_argument("--cwd", default=None,
                   help="override cwd (for repo-scoped resolution)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true", dest="as_json")
    sub = p.add_subparsers(dest="verb")
    sub.required = False  # default to 'show'

    sub.add_parser("show").add_argument("category", nargs="?", default=None)
    sub.add_parser("get").add_argument("key")
    sub.add_parser("describe").add_argument("key")
    sub.add_parser("options").add_argument("key")
    s = sub.add_parser("set"); s.add_argument("key"); s.add_argument("value")
    sub.add_parser("reset").add_argument("key")
    sub.add_parser("reset-all")
    sub.add_parser("diff")
    sub.add_parser("export")
    sub.add_parser("mastery")
    sub.add_parser("mastery-reset").add_argument("rule_id")
    sub.add_parser("mastery-reset-all")
    s_sources = sub.add_parser("sources")
    s_sources.add_argument("rule_id", nargs="?", default=None)

    args = p.parse_args(argv)
    cwd = Path(args.cwd) if args.cwd else Path.cwd()
    verb = args.verb or "show"

    if verb == "show":
        return cmd_show(cwd, getattr(args, "category", None), args.as_json)
    if verb == "get":
        return cmd_get(cwd, args.key, args.as_json)
    if verb == "describe":
        return cmd_describe(cwd, args.key, args.as_json)
    if verb == "set":
        return cmd_set(cwd, args.key, args.value, args.scope, args.dry_run)
    if verb == "reset":
        return cmd_reset(cwd, args.key, args.scope, args.dry_run)
    if verb == "reset-all":
        return cmd_reset_all(cwd, args.scope, args.dry_run)
    if verb == "diff":
        return cmd_diff(cwd, args.as_json)
    if verb == "export":
        return cmd_export(cwd, args.as_json)
    if verb == "options":
        return cmd_options(cwd, args.key, args.as_json)
    if verb == "mastery":
        return cmd_mastery(cwd, args.as_json)
    if verb == "mastery-reset":
        return cmd_mastery_reset(cwd, args.rule_id, args.dry_run)
    if verb == "mastery-reset-all":
        return cmd_mastery_reset_all(cwd, args.dry_run)
    if verb == "sources":
        return cmd_sources(cwd, args.rule_id, args.as_json)
    print(f"unknown verb: {verb}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
