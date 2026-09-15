---
name: review-agents
description: Use for PR review, test runs, or dependency audits with the shipped specialist agents.
---

# Review agents

Select the requested specialist: `pr-reviewer`, `test-runner`, or
`dependency-auditor`. Their complete definitions live at `../../agents/<name>.md`
relative to this skill. Read the selected file and preserve its full checklist,
tool restrictions, build commands, and report format. Do not substitute a summary.

In Claude Code dispatch the corresponding installed plugin agent. In Codex read
[the dispatch adapter](references/codex-tools.md), then send the full definition
and review scope to a child. If agent tools are unavailable, execute that complete
procedure in the current context and state that it was a single-context review.
Reviewers report findings; they do not silently fix source or publish changes.
