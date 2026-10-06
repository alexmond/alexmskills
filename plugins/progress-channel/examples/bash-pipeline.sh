#!/usr/bin/env bash
# A pipeline whose stages nest under it, with no token passed around.
#
#   ⏳ example pipeline ████████░░░░░░░░░░  50% 1/3 · ~4s left
#   ⏳   ↳ stage: test  ████████████░░░░░░  66% 4/6
#
# The pipeline registers once and exports PROGRESS_PARENT. Every `progress
# start` below it — in this script, in a sub-script, in a `progress run`, or in
# a tap — reads that variable and nests itself. Sub-scripts need no changes:
# stage 2 here is ./bash-loop.sh, which knows nothing about pipelines.
#
#   ./bash-pipeline.sh
#   FAIL_AT=4 ./bash-pipeline.sh    # a failed stage closes the pipeline too
set -euo pipefail

DELAY=${DELAY:-0.05}
HERE=$(cd "$(dirname "$0")" && pwd)
progress() { [ -n "${PROGRESS_CLI:-}" ] && $PROGRESS_CLI "$@" 2>/dev/null || true; }

T=$(progress start --name 'example pipeline' --total 3 --pid $$)
# Finishing the parent also closes any stage still open, so a failure never
# leaves a child row dangling.
trap 'rc=$?
      if [ -n "$T" ]; then
        if [ "$rc" -eq 0 ]; then progress finish "$T"
        else progress finish "$T" --fail "pipeline failed (exit $rc)"; fi
      fi' EXIT
[ -n "$T" ] && export PROGRESS_PARENT=$T

# Stage 1 — a counted loop, written inline.
S=$(progress start --name 'stage: fetch' --total 5 --pid $$)
for i in 1 2 3 4 5; do sleep "$DELAY"; [ -n "$S" ] && progress step "$S"; done
[ -n "$S" ] && progress finish "$S"
[ -n "$T" ] && progress step "$T" --detail fetch

# Stage 2 — an existing script, unmodified. It nests because of the export.
ITEMS=6 DELAY="$DELAY" FAIL_AT="${FAIL_AT:-}" "$HERE/bash-loop.sh" >/dev/null
[ -n "$T" ] && progress step "$T" --detail loop

# Stage 3 — an opaque command: `run` times it and learns how long it takes.
if [ -n "${PROGRESS_CLI:-}" ]; then
  $PROGRESS_CLI run --name 'stage: package' -- sleep "$DELAY" >/dev/null
else
  sleep "$DELAY"
fi
[ -n "$T" ] && progress step "$T" --detail package
echo "pipeline done"
