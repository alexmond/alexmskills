#!/usr/bin/env bash
# backlog-snapshot.sh — read-only facts for a triage round.
# Prints: open issues, open PRs, git worktrees, recent CI runs on the default
# branch. Starts nothing, stops nothing. --brief prints issues + PRs only.
# Repo-specific facts (running instances, roadmap markers) come from an
# optional extension: .claude/ticket-triage/snapshot-extra.sh in the repo.
set -euo pipefail

BRIEF=0
[ "${1:-}" = "--brief" ] && BRIEF=1

section() { printf '\n== %s ==\n' "$1"; }

section "open issues"
gh issue list --state open --limit 100 \
  --json number,title,labels,updatedAt \
  -q '.[] | "#\(.number) [\(.labels | map(.name) | join(","))] \(.title) (updated \(.updatedAt[:10]))"' \
  || echo "(gh issue list failed — no repo, no auth, or no tracker)"

section "open PRs"
gh pr list --state open --limit 50 \
  --json number,title,headRefName,isDraft,statusCheckRollup \
  -q '.[] | "#\(.number)\(if .isDraft then " [draft]" else "" end) \(.title) <- \(.headRefName) checks:\([.statusCheckRollup[]?.conclusion // "pending"] | unique | join(","))"' \
  || echo "(gh pr list failed)"

if [ "$BRIEF" = "0" ]; then
  section "worktrees"
  git worktree list 2>/dev/null || echo "(not a git repo)"

  section "recent runs on the default branch"
  DEFAULT_BRANCH=$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name 2>/dev/null || echo main)
  gh run list --branch "$DEFAULT_BRANCH" --limit 5 \
    --json displayTitle,conclusion,updatedAt \
    -q '.[] | "\(.conclusion // "in_progress")  \(.displayTitle[:70])  (\(.updatedAt[:16]))"' \
    || echo "(gh run list failed — no CI or no auth)"

  EXTRA=".claude/ticket-triage/snapshot-extra.sh"
  if [ -x "$EXTRA" ] || [ -f "$EXTRA" ]; then
    section "repo-specific (snapshot-extra.sh)"
    bash "$EXTRA" || echo "(snapshot-extra.sh failed — fix it; a broken instrument outranks features)"
  fi
fi
