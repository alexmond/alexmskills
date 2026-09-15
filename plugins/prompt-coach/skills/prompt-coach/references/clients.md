# Claude Code and Codex

Both clients run the same analyzer before a submitted prompt and receive
`hookSpecificOutput.additionalContext`. The assistant renders coaching in its
response; no ANSI output or custom status bar is required. Preserve the user's
task and constraints when applying a rewrite.

## Registration

- Claude Code loads `hooks/hooks.json` using `CLAUDE_PLUGIN_ROOT`.
- Codex loads `hooks/codex.json` through the generated manifest, using
  `PLUGIN_ROOT`. Baseline: Codex CLI 0.154.0 with native `UserPromptSubmit` hooks.
  After installing/updating, use `/hooks` to review and trust the definition.
  A changed definition requires another review.
- Register once per client. Adding a user hook alongside the plugin hook
  would analyze and count each prompt twice.

## State and transcripts

Both clients intentionally share `~/.claude/prompt-coach` and the consuming
repo's `.claude/prompt-coach`: mastery, configuration, and history carry over.
These data paths do not require Claude Code to be installed. The existing
per-repo acceptance window is also shared; concurrent sessions in the same
repo are not isolated. Separate worktrees provide separate local state.

The hook's `transcript_path` is authoritative, including null or missing files.
Claude session IDs resolve to their own transcript. Only legacy inputs without
session metadata fall back to the latest Claude transcript. Codex events never
fall back to Claude history.

Codex response-item assistant messages, question-tool calls, and agent-message
events are normalized for clarification detection and rejection timing.
Unknown transcript formats degrade to prompt-only analysis. Transcripts are
not a stable Codex API; keep fixtures current when they change.

For interactive configuration, use the client's available question tool or
plain text rather than requiring Claude's `AskUserQuestion` tool name.

## Commands in Codex

Use natural-language requests for stats, config, mastery, library, dashboard,
help, analyze, and report-issue. Read the corresponding `commands/<verb>.md`
under the plugin root. Resolve scripts relative to that root, not a different
client's cache. The root is two levels above the `skills/prompt-coach` directory;
`scripts/config.py` and `scripts/serve.py` are shared by both clients.

Official contract: https://learn.chatgpt.com/docs/hooks
