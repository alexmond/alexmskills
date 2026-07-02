#!/usr/bin/env bash
# Scaffold a new plugin in the beta channel and register it in beta/.claude-plugin/marketplace.json.
# Usage: scripts/new-beta-plugin.sh <name>
set -euo pipefail

name="${1:-}"
[ -n "$name" ] || { echo "Usage: $0 <plugin-name>" >&2; exit 1; }
case "$name" in *[!a-z0-9-]*) echo "Name must be kebab-case (a-z 0-9 -)." >&2; exit 1;; esac

root="$(cd "$(dirname "$0")/.." && pwd)"
beta_mp="$root/beta/.claude-plugin/marketplace.json"
pdir="$root/beta/plugins/$name"

[ -d "$pdir" ] && { echo "Beta plugin '$name' already exists." >&2; exit 1; }

mkdir -p "$pdir/.claude-plugin" "$pdir/skills/$name"

cat > "$pdir/.claude-plugin/plugin.json" <<JSON
{
  "name": "$name",
  "description": "TODO: one-sentence description of $name (beta).",
  "version": "0.1.0",
  "author": { "name": "Alex Mondshain", "email": "alexmond@gmail.com" },
  "homepage": "https://www.alexmond.org/alexmskills/",
  "repository": "https://github.com/alexmond/alexmskills",
  "license": "MIT",
  "keywords": []
}
JSON

cat > "$pdir/skills/$name/SKILL.md" <<MD
---
name: $name
description: TODO — what this skill does and when Claude should use it (beta, unreleased).
---

# $name

TODO: write the skill. This is a beta-channel plugin; promote it to stable with
\`make promote PLUGIN=$name\` once it is ready.
MD

# Register in the beta marketplace (skip if already present).
tmp="$(mktemp)"
jq --arg n "$name" --arg src "./beta/plugins/$name" '
  if any(.plugins[]; .name == $n) then .
  else .plugins += [{
    name: $n,
    displayName: $n,
    source: $src,
    description: ("TODO: " + $n + " (beta)"),
    version: "0.1.0",
    category: "beta",
    keywords: []
  }] end
' "$beta_mp" > "$tmp" && mv "$tmp" "$beta_mp"

echo "Scaffolded beta plugin: beta/plugins/$name"
echo "Registered in: $beta_mp"
echo "Next: edit the SKILL.md + plugin.json, then 'make validate'."
