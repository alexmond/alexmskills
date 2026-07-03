#!/usr/bin/env bash
# dev-link — symlink a plugin's cache-dir to the live source tree so
# /reload-plugins picks up edits without an /plugin uninstall + install
# dance. Version-aware: reads the currently-installed version from
# installed_plugins.json and creates the symlink at that path.
#
# Usage:
#   scripts/dev-link.sh <plugin-name> [<marketplace-name>]     # default marketplace: alexmskills
#   scripts/dev-link.sh --unlink <plugin-name>                 # remove the symlink
#
# After bumping a plugin version (make bump), re-run this to relink.

set -euo pipefail

INSTALLED_PLUGINS_JSON="${INSTALLED_PLUGINS_JSON:-$HOME/.claude/plugins/installed_plugins.json}"
CACHE_ROOT="${CACHE_ROOT:-$HOME/.claude/plugins/cache}"

usage() { echo "usage: $0 [--unlink] <plugin-name> [<marketplace>]" >&2; exit 2; }

unlink_mode=false
if [ "${1:-}" = "--unlink" ]; then
  unlink_mode=true
  shift
fi

plugin="${1:-}"
marketplace="${2:-alexmskills}"
[ -n "$plugin" ] || usage

# Find the current install version from installed_plugins.json
key="${plugin}@${marketplace}"
version=$(jq -r --arg k "$key" '.plugins[$k][0].version // empty' "$INSTALLED_PLUGINS_JSON" 2>/dev/null || true)
if [ -z "$version" ]; then
  echo "no install found for '$key' in $INSTALLED_PLUGINS_JSON" >&2
  echo "install it once via /plugin install $plugin@$marketplace, then re-run." >&2
  exit 1
fi

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
source_dir="$repo_root/plugins/$plugin"
cache_dir="$CACHE_ROOT/$marketplace/$plugin/$version"

if [ ! -d "$source_dir" ]; then
  echo "source dir not found: $source_dir" >&2
  exit 1
fi

if $unlink_mode; then
  if [ -L "$cache_dir" ]; then
    rm -f "$cache_dir"
    echo "removed symlink: $cache_dir"
    echo "next /plugin install / update will re-materialize the cache with a real copy."
  else
    echo "not a symlink (or missing): $cache_dir — nothing to unlink"
  fi
  exit 0
fi

# Link mode. Preserve any .in_use lock markers Claude Code has written.
if [ -d "$cache_dir/.in_use" ] && [ ! -L "$cache_dir" ]; then
  echo "preserving $(ls "$cache_dir/.in_use" | wc -l) .in_use lock markers"
  mkdir -p "$source_dir/.in_use"
  cp -n "$cache_dir/.in_use/"* "$source_dir/.in_use/" 2>/dev/null || true
fi

rm -rf "$cache_dir"
ln -s "$source_dir" "$cache_dir"

echo "linked:  $cache_dir"
echo "         -> $source_dir"
echo
echo "next: /reload-plugins in Claude Code to pick up the current source."
echo "when you edit files, no reinstall is needed - just /reload-plugins."
