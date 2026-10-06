#!/usr/bin/env bash
# A loop that reports itself: start / step / finish.
#
#   ./bash-loop.sh                  # 20 items
#   ITEMS=200 DELAY=0.01 ./bash-loop.sh
#   FAIL_AT=7 ./bash-loop.sh        # see a failure reported with its reason
#
# Without PROGRESS_CLI this is a plain script: every progress call is a no-op.
set -euo pipefail

ITEMS=${ITEMS:-20}
DELAY=${DELAY:-0.05}
FAIL_AT=${FAIL_AT:-}

# One function is the whole integration. It never fails the script: a progress
# bar is not worth a broken job.
progress() { [ -n "${PROGRESS_CLI:-}" ] && $PROGRESS_CLI "$@" 2>/dev/null || true; }

# --pid $$ matters here. The channel watches the process that started a job
# and marks the job orphaned if that process dies. Called through a function
# inside $( ), the CLI's parent is a short-lived subshell, not this script —
# so say which process is the real owner. ($$ is the script's pid even inside
# a subshell.) Calling the CLI directly, `T=$($PROGRESS_CLI start …)`, needs
# no --pid.
T=$(progress start --name 'bash loop' --total "$ITEMS" --pid $$)

# EXIT, not ERR: an ERR trap does not fire inside a function without `set -E`.
# EXIT runs on every way out, so the job is closed whether the loop finishes,
# fails, or is interrupted.
trap 'rc=$?
      if [ -n "$T" ]; then
        if [ "$rc" -eq 0 ]; then progress finish "$T"
        else progress finish "$T" --fail "stopped at item ${i:-?} (exit $rc)"; fi
      fi' EXIT

for i in $(seq 1 "$ITEMS"); do
  sleep "$DELAY"                                  # ← the real work goes here
  [ "$i" = "$FAIL_AT" ] && { echo "item $i failed" >&2; exit 3; }
  # --count adds to named tallies; --detail is the line shown beside the bar.
  [ -n "$T" ] && progress step "$T" --count ok=1 --detail "item $i"
done
echo "processed $ITEMS items"
