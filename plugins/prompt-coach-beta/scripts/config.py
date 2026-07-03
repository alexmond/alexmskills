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
    s = sub.add_parser("set"); s.add_argument("key"); s.add_argument("value")
    sub.add_parser("reset").add_argument("key")
    sub.add_parser("reset-all")
    sub.add_parser("diff")
    sub.add_parser("export")

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
    print(f"unknown verb: {verb}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
