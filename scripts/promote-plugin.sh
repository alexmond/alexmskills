#!/usr/bin/env bash
# Promote a plugin from the beta channel to the stable marketplace.
#   - moves beta/plugins/<name> -> plugins/<name>
#   - removes its entry from beta/.claude-plugin/marketplace.json
#   - adds an entry to .claude-plugin/marketplace.json (carrying over description/keywords/category)
# Usage: scripts/promote-plugin.sh <name>
set -euo pipefail

name="${1:-}"
[ -n "$name" ] || { echo "Usage: $0 <plugin-name>" >&2; exit 1; }

root="$(cd "$(dirname "$0")/.." && pwd)"
stable_mp="$root/.claude-plugin/marketplace.json"
beta_mp="$root/beta/.claude-plugin/marketplace.json"
src="$root/beta/plugins/$name"
dst="$root/plugins/$name"

[ -d "$src" ] || { echo "No beta plugin at $src" >&2; exit 1; }
[ -d "$dst" ] && { echo "Stable plugin '$name' already exists at $dst" >&2; exit 1; }

# Carry the beta marketplace entry forward (fallback to a minimal entry if absent).
entry="$(jq --arg n "$name" '.plugins[] | select(.name==$n)' "$beta_mp")"
[ -n "$entry" ] || entry="$(jq -n --arg n "$name" --arg src "./plugins/$name" '{name:$n, source:$src}')"

# Move the plugin directory (git mv if tracked, else plain mv).
if git -C "$root" ls-files --error-unmatch "beta/plugins/$name" >/dev/null 2>&1; then
  git -C "$root" mv "beta/plugins/$name" "plugins/$name"
else
  mv "$src" "$dst"
fi

# Remove from beta catalog.
tmp="$(mktemp)"
jq --arg n "$name" 'del(.plugins[] | select(.name==$n))' "$beta_mp" > "$tmp" && mv "$tmp" "$beta_mp"

# Add to stable catalog. Source is the clone-root-relative bare-string form
# (verified: Claude Code resolves bare-string plugin sources from the marketplace
# clone root, not from the marketplace.json's parent directory).
tmp="$(mktemp)"
jq --argjson e "$entry" --arg n "$name" --arg src "./plugins/$name" '
  .plugins += [ ($e + { source: $src }) ]
' "$stable_mp" > "$tmp" && mv "$tmp" "$stable_mp"

echo "Promoted '$name': beta/plugins -> plugins; updated both marketplace manifests."
echo "Next:"
echo "  1. make bump PLUGIN=$name VERSION=1.0.0   # set a real release version"
echo "  2. add docs/modules/ROOT/pages/$name.adoc + a nav.adoc entry"
echo "  3. make validate"
