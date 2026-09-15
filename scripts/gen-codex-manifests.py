#!/usr/bin/env python3
"""Generate the Codex-side packaging from the Claude-side source of truth.

Two ecosystems, one catalog. Superpowers (the reference implementation of a
cross-harness skills repo) hand-maintains six per-harness manifests and pays
for it with a nine-entry `.version-bump.json` that stamps the version into all
of them — a list that fails the day someone adds a seventh. Here the Codex
manifests are DERIVED from `.claude-plugin/*` instead, so drift is not
prevented by discipline, it is impossible: regenerate and diff.

Writes:
  plugins/<name>/.codex-plugin/plugin.json   one per catalogued plugin
  .agents/plugins/marketplace.json           the Codex-side marketplace

    python3 scripts/gen-codex-manifests.py            # write
    python3 scripts/gen-codex-manifests.py --check    # verify in sync (CI)

Compatibility tiers are computed from the TREE, never hand-listed, so a plugin
that gains hooks tomorrow is re-tiered by the next run:

  1 portable   prose skills — behave the same on any harness
  2 subagents  spawns agents; needs the tool-name translation in
               skills/*/references/codex-tools.md (Agent -> spawn_agent etc.)
  3 hooks      ships lifecycle hooks. A reviewed hooks/codex.json opts into
               Codex execution; other plugins remain advisory until adapted.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODEX_MARKET = ROOT / ".agents" / "plugins" / "marketplace.json"

# Codex/AppStore-style categories, mapped from this repo's own taxonomy.
CATEGORY = {
    "self-learning": "Developer Tools",
    "workflow": "Developer Tools",
    "development": "Developer Tools",
    "research": "Productivity",
    "review": "Developer Tools",
    "beta": "Developer Tools",
}

TIER_NOTE = {
    2: ("Uses client-specific agent or CLI tools. Follow the skill's "
        "references/codex-tools.md and the live tool schema; enable multi-agent "
        "only for workflows that actually dispatch subagents."),
    3: ("Ships Claude Code hooks that this plugin has not yet adapted for "
        "Codex. Automatic hook behavior is disabled here; skill instructions "
        "remain advisory."),
}


SPAWN_SMELL = re.compile(
    r"\bTask tool\b|\bAgent tool\b|subagent_type|\bparallel agents\b|"
    r"\b(spawn|launch|dispatch|convene)\w*\b[^.\n]{0,40}\bagents?\b|"
    r"\bas a subagent\b|\bclaude -p\b", re.I)


def signals(plugin_dir: Path) -> dict:
    """Tiering reads ARTIFACTS, not prose.

    Prose detection was tried and cut: it put skill-linter in tier 2 because
    its rule text talks about fan-out, and left conductor in tier 1 although
    the whole skill is about supervising parallel lanes. A regex over English
    cannot tell a skill that spawns agents from one that describes spawning.

    So the author declares the tier by shipping the artifact — a
    references/codex-tools.md is itself the statement "this needs translation"
    — and the smell only WARNS about a plugin that looks like it should have
    one. Structure is unambiguous; prose is not.
    """
    hooks = any((plugin_dir / "hooks" / f).exists() for f in ("hooks.json", "codex.json"))
    agents = (plugin_dir / "agents").is_dir()
    xlat = any(plugin_dir.glob("skills/*/references/codex-tools.md"))
    smell = False
    for f in list(plugin_dir.glob("skills/*/SKILL.md")) + list(plugin_dir.glob("commands/*.md")):
        if SPAWN_SMELL.search(f.read_text(encoding="utf-8", errors="replace")):
            smell = True
            break
    return {"hooks": hooks, "codex_hooks": (plugin_dir / "hooks" / "codex.json").is_file(),
            "agents": agents, "xlat": xlat, "smell": smell,
            "tier": 3 if hooks else 2 if (agents or xlat) else 1}


def default_prompts(desc: str, name: str) -> list[str]:
    """Real trigger phrases beat invented ones — every description in this
    catalog quotes what people actually type, so lift those."""
    quoted = re.findall(r'"([^"]{6,60})"', desc)
    out = [q for q in quoted if not q.startswith("/")][:2]
    return out or [f"Use {name}."]


def build(plugin: dict) -> tuple[Path, dict]:
    name = plugin["name"]
    pdir = ROOT / "plugins" / name
    manifest = json.loads((pdir / ".claude-plugin" / "plugin.json").read_text())
    sig = signals(pdir)
    t = sig["tier"]
    desc = manifest.get("description", plugin.get("description", ""))
    notes = [TIER_NOTE[n] for n in (3, 2)
             if (n == 3 and sig["hooks"]) or (n == 2 and (sig["agents"] or sig["xlat"]))]
    if sig["codex_hooks"]:
        notes = [note for note in notes if note != TIER_NOTE[3]]
        notes.append("Includes Codex lifecycle hooks. Review and trust them "
                     "with /hooks before they run.")
    long_desc = " ".join([desc] + notes)
    out = {
        "name": name,
        "version": manifest["version"],
        "description": desc,
        "author": manifest.get("author", {}),
        "homepage": manifest.get("homepage", ""),
        "repository": manifest.get("repository", ""),
        "license": manifest.get("license", "MIT"),
        "keywords": manifest.get("keywords", []),
        "skills": "./skills/",
        # Opt in per plugin after adapting and testing its runtime behavior.
        "hooks": "./hooks/codex.json" if sig["codex_hooks"] else {},
        "compatibility": {
            "tier": t,
            "enforcement": "claude-code-and-codex" if sig["codex_hooks"] else
                           "claude-code" if sig["hooks"] else "portable",
            "needsToolTranslation": bool(sig["agents"] or sig["xlat"]),
        },
        "interface": {
            "displayName": plugin.get("displayName", name),
            "shortDescription": desc.split(".")[0][:120],
            "longDescription": long_desc,
            "developerName": manifest.get("author", {}).get("name", ""),
            "category": CATEGORY.get(plugin.get("category", ""), "Developer Tools"),
            "capabilities": ["Interactive", "Read", "Write"],
            "defaultPrompt": default_prompts(desc, name),
            "websiteURL": manifest.get("homepage", ""),
        },
    }
    return pdir / ".codex-plugin" / "plugin.json", out


def main(argv: list[str]) -> int:
    check = "--check" in argv
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    entries, stale = [], []

    for plugin in market["plugins"]:
        path, manifest = build(plugin)
        text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
        if check:
            if not path.exists() or path.read_text() != text:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        hook_config = ROOT / "plugins" / plugin["name"] / "hooks" / "codex.json"
        if hook_config.exists() and "codex-bridge.py" in hook_config.read_text():
            bridge = hook_config.with_name("codex-bridge.py")
            source = (ROOT / "scripts" / "codex-hook-bridge.py").read_text()
            if check:
                if not bridge.exists() or bridge.read_text() != source:
                    stale.append(str(bridge.relative_to(ROOT)))
            else:
                bridge.write_text(source)
        entries.append({
            "name": plugin["name"],
            "source": {"source": "url", "url": f"./plugins/{plugin['name']}"},
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
            "category": CATEGORY.get(plugin.get("category", ""), "Developer Tools"),
        })

    codex_market = {
        "name": market["name"],
        "interface": {"displayName": market.get("description", market["name"])[:60]},
        "plugins": entries,
    }
    text = json.dumps(codex_market, indent=2, ensure_ascii=False) + "\n"
    if check:
        if not CODEX_MARKET.exists() or CODEX_MARKET.read_text() != text:
            stale.append(str(CODEX_MARKET.relative_to(ROOT)))
        if stale:
            print("Codex manifests are STALE — run `make codex`:")
            for s in stale:
                print(f"  {s}")
            return 1
        print(f"Codex manifests in sync ({len(entries)} plugins).")
        return 0

    CODEX_MARKET.parent.mkdir(parents=True, exist_ok=True)
    CODEX_MARKET.write_text(text, encoding="utf-8")
    tiers, missing = {}, []
    for plugin in market["plugins"]:
        sig = signals(ROOT / "plugins" / plugin["name"])
        tiers.setdefault(sig["tier"], []).append(plugin["name"])
        if sig["smell"] and not sig["xlat"] and not sig["agents"]:
            missing.append(plugin["name"])
    print(f"Wrote {len(entries)} Codex plugin manifests + {CODEX_MARKET.relative_to(ROOT)}")
    for t in sorted(tiers):
        print(f"  tier {t}: {len(tiers[t])} — {', '.join(sorted(tiers[t]))}")
    if missing:
        print("\n  ⚠ looks like it spawns agents but ships no "
              "skills/*/references/codex-tools.md:")
        print("    " + ", ".join(sorted(missing)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
