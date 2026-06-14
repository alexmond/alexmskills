#!/usr/bin/env bash
# Validate every marketplace channel and the plugin manifests it references.
# Pure jq + bash — no Claude Code CLI required, so it runs anywhere (incl. CI).
#
# Channels validated:
#   - stable: .claude-plugin/marketplace.json
#   - beta:   beta/.claude-plugin/marketplace.json   (if present)
#
# Per channel, for each plugin entry:
#   - the plugin dir + .claude-plugin/plugin.json exist
#   - plugin.json is valid JSON, name matches the marketplace entry, has a version
#   - the plugin ships at least one component dir (skills/ agents/ commands/)
#
# Exit non-zero on any hard error; warnings do not fail the build.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
fail=0

note() { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
warn() { printf '  \033[33mWARN\033[0m %s\n' "$1"; }
err()  { printf '  \033[31mFAIL\033[0m %s\n' "$1"; fail=1; }

validate_channel() {
  local mp="$1"
  local base; base="$(cd "$(dirname "$mp")/.." && pwd)"   # marketplace root = parent of .claude-plugin
  echo "Validating $(jq -r '.name // "?"' "$mp" 2>/dev/null) — $mp"

  if ! jq empty "$mp" 2>/dev/null; then err "marketplace.json is not valid JSON"; return; fi
  [ "$(jq -r '.name // empty' "$mp")" ] || err "missing .name"
  [ "$(jq -r '.owner.name // empty' "$mp")" ] || err "missing .owner.name"

  local plugin_root; plugin_root="$(jq -r '.metadata.pluginRoot // "."' "$mp")"; plugin_root="${plugin_root#./}"
  local count; count="$(jq '.plugins | length' "$mp")"
  if [ "$count" -eq 0 ]; then warn "no plugins yet (empty channel)"; return; fi

  while read -r name; do
    local src_type src_path dir manifest pname ver
    src_type="$(jq -r --arg n "$name" '.plugins[] | select(.name==$n) | .source | type' "$mp")"
    if [ "$src_type" = "object" ]; then
      # Explicit { source: github, repo, path } form — path is repo-root-relative
      src_path="$(jq -r --arg n "$name" '.plugins[] | select(.name==$n) | .source.path // ""' "$mp")"
      dir="$root/$src_path"
    else
      # Bare-string form — resolve under pluginRoot, relative to the channel base
      src_path="$(jq -r --arg n "$name" '.plugins[] | select(.name==$n) | .source' "$mp")"
      dir="$base/${plugin_root:+$plugin_root/}$src_path"
    fi
    manifest="$dir/.claude-plugin/plugin.json"

    if [ ! -f "$manifest" ]; then err "$name: missing $manifest"; continue; fi
    if ! jq empty "$manifest" 2>/dev/null; then err "$name: plugin.json is not valid JSON"; continue; fi

    pname="$(jq -r '.name // empty' "$manifest")"
    [ "$pname" = "$name" ] || err "$name: plugin.json name '$pname' != marketplace entry '$name'"

    ver="$(jq -r '.version // empty' "$manifest")"
    [ -n "$ver" ] || warn "$name: no version in plugin.json (will track commit SHA)"

    if [ ! -d "$dir/skills" ] && [ ! -d "$dir/agents" ] && [ ! -d "$dir/commands" ]; then
      warn "$name: no skills/ agents/ commands/ component dir"
    fi

    note "$name ($ver)"
  done < <(jq -r '.plugins[].name' "$mp")
}

validate_channel "$root/.claude-plugin/marketplace.json"
if [ -f "$root/beta/.claude-plugin/marketplace.json" ]; then
  echo
  validate_channel "$root/beta/.claude-plugin/marketplace.json"
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "All channels valid."
else
  echo "Validation failed." >&2
fi
exit "$fail"
