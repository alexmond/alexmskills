#!/usr/bin/env bash
# Validate the marketplace + the plugin manifests it references.
# Pure jq + bash — no Claude Code CLI required, so it runs anywhere (incl. CI).
#
# One channel, one catalog: .claude-plugin/marketplace.json at the repo root.
# In-progress plugins live alongside stable ones under plugins/ with a
# `-beta` suffix in the name (e.g. `prompt-coach-beta`) — no separate
# marketplace file, no dual clone-root logic, no extraKnownMarketplaces
# needed on the consumer side.
#
# For each plugin entry:
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
    local src_type src_inner src_path dir manifest pname ver
    src_type="$(jq -r --arg n "$name" '.plugins[] | select(.name==$n) | .source | type' "$mp")"
    if [ "$src_type" = "object" ]; then
      src_inner="$(jq -r --arg n "$name" '.plugins[] | select(.name==$n) | .source.source // ""' "$mp")"
      src_path="$(jq -r --arg n "$name" '.plugins[] | select(.name==$n) | .source.path // ""' "$mp")"
      # Guard: the `github` source type does NOT support `path` — it silently
      # ignores it, cloning the full repo and using the repo root as the
      # plugin root. Skills/hooks/plugin.json then never resolve. For own-repo
      # plugins use the bare-string form (`"./plugins/<name>"`); for plugins
      # in a different repo use `git-subdir`. See anthropics/claude-code#43811.
      if [ "$src_inner" = "github" ] && [ -n "$src_path" ]; then
        err "$name: source uses {source: \"github\", path: \"$src_path\"} — \"github\" silently ignores path. Use bare-string \"./$src_path\" (own-repo) or \"git-subdir\" (cross-repo)."
        continue
      fi
      # Otherwise the object form's path is repo-root-relative for validation.
      dir="$root/$src_path"
    else
      # Bare-string form — resolve relative to REPO ROOT, not the marketplace
      # dir. Claude Code treats bare-string plugin sources as clone-root-relative
      # (verified empirically: install of a subdir marketplace fails on
      # "Source path does not exist: <clone_root>/plugins/<name>" rather than
      # <clone_root>/<subdir>/plugins/<name>). For the stable channel this is
      # the same directory; for the beta channel the sources must include the
      # channel prefix (e.g. "./beta/plugins/<name>").
      src_path="$(jq -r --arg n "$name" '.plugins[] | select(.name==$n) | .source' "$mp")"
      dir="$root/${src_path#./}"
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

echo
if [ "$fail" -eq 0 ]; then
  echo "Marketplace valid."
else
  echo "Validation failed." >&2
fi
exit "$fail"
