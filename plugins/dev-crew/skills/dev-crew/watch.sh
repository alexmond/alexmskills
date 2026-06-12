#!/usr/bin/env bash
# watch.sh — live feed of the active dev-crew run directory.
#
# Follows the most recent run under <repo>/.claude/dev-crew/runs/ and prints
# each role's handoff file (PLAN.md, CONTRACT.md, CHANGES.md, QA.md, DEPLOY.md,
# DIAGNOSIS.md, PROFILE.md ...) the moment it appears or changes — so you get a
# live window into what the crew is actually producing, alongside your main
# Claude Code session. Run it in a second pane.
#
# Usage:
#   ./watch.sh                  # follow the most recent run in this repo
#   ./watch.sh <run-id>         # pin to a specific run directory
#   ./watch.sh -i 1             # poll interval in seconds (default 2)
#   ./watch.sh -r /path/to/repo # repo root (default: git toplevel, else cwd)
#   ./watch.sh -h               # help
#
# No dependencies beyond bash + coreutils. Works on Linux and macOS.

set -euo pipefail

INTERVAL=2
REPO=""
RUN_ID=""

usage() { awk 'NR>1{ if($0 !~ /^#/) exit; sub(/^# ?/,""); print }' "$0"; exit 0; }

while getopts ":i:r:h" opt; do
  case "$opt" in
    i) INTERVAL="$OPTARG" ;;
    r) REPO="$OPTARG" ;;
    h) usage ;;
    \?) echo "unknown option -$OPTARG" >&2; exit 2 ;;
    :) echo "option -$OPTARG needs a value" >&2; exit 2 ;;
  esac
done
shift $((OPTIND - 1))
[ "${1:-}" ] && RUN_ID="$1"

# Resolve repo root.
if [ -z "$REPO" ]; then
  REPO="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
fi
RUNS="$REPO/.claude/dev-crew/runs"

# Portable mtime (epoch seconds): GNU stat, then BSD/macOS stat.
mtime() { stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null || echo 0; }

# Color only when attached to a terminal.
if [ -t 1 ] && command -v tput >/dev/null 2>&1 && [ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]; then
  C_HDR="$(tput setaf 6)"; C_DIM="$(tput setaf 8 2>/dev/null || tput setaf 4)"; C_OFF="$(tput sgr0)"
else
  C_HDR=""; C_DIM=""; C_OFF=""
fi

resolve_run() {
  if [ -n "$RUN_ID" ]; then
    printf '%s\n' "$RUNS/$RUN_ID"
  else
    ls -1dt "$RUNS"/*/ 2>/dev/null | head -1
  fi
}

echo "${C_HDR}dev-crew watch${C_OFF}  repo: $REPO"
echo "${C_DIM}waiting for a run under $RUNS … (Ctrl-C to quit)${C_OFF}"

declare -A SEEN          # file -> last mtime printed
CUR_RUN=""

emit() {                 # emit <file>
  local f="$1" name ts
  name="$(basename "$f")"
  ts="$(date '+%H:%M:%S')"
  echo
  echo "${C_HDR}┌─ $name${C_OFF}  ${C_DIM}$ts${C_OFF}"
  # handoff files are short; cap defensively at 300 lines
  sed 's/^/│ /' "$f" | head -300
  echo "${C_HDR}└─${C_OFF}"
}

while true; do
  run="$(resolve_run || true)"
  if [ -n "$run" ] && [ -d "$run" ]; then
    if [ "$run" != "$CUR_RUN" ]; then
      CUR_RUN="$run"
      SEEN=()
      echo
      echo "${C_HDR}▶ following run:${C_OFF} $(basename "$CUR_RUN")"
    fi
    # newest-modified first so the feed reads in event order
    while IFS= read -r f; do
      [ -f "$f" ] || continue
      m="$(mtime "$f")"
      if [ "${SEEN[$f]:-0}" != "$m" ]; then
        SEEN["$f"]="$m"
        emit "$f"
      fi
    done < <(ls -1t "$CUR_RUN"/*.md 2>/dev/null | tac)
  fi
  sleep "$INTERVAL"
done
