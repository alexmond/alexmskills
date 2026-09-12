# Running this skill on Codex

Claude Code is this skill's native harness. The **method is unchanged** here —
only tool names and one config switch differ. Codex's multi-agent surface has
shipped more than one version, so **trust your actual tool list over this table
when they disagree**.

## Enable multi-agent

`~/.codex/config.toml`:

```toml
[features]
multi_agent = true
```

Without it the spawn tools this skill needs are absent and the skill degrades to
doing the work in one context.

## Tool mapping

| This skill says | On Codex |
|---|---|
| dispatch N agents in parallel (one message, N `Agent` calls) | one `spawn_agent` per worker; `fork_turns: "none"` gives a clean context — the default `"all"` copies your whole transcript into each child |
| a worker's result comes back | `wait_agent` — an event subscription, not a poll. Wait in 5–10 minute stretches (`timeout_ms` 300000–600000); short polls cost a tool call and a context rebill for nothing |
| send a correction to a running worker | `followup_task` (it also transparently reloads a child the harness evicted) |
| what is still running | `list_agents` |
| an agent definition in `agents/<role>.md` | a role file under `~/.codex/agents/`, selected with `agent_type` on an isolated fork |
| per-role model tier | set **both** `model` and `reasoning_effort` on every spawn — setting `model` alone silently resets effort to that model's default |

Consider a machine-level backstop so a spawn that slips through still routes
deliberately:

```toml
[agents]
default_subagent_model = "<a mid-tier model from your spawn allowlist>"
default_subagent_reasoning_effort = "medium"
```

## Worktree detection is identical

The isolation test this skill uses is plain git and needs no translation:

```bash
GIT_DIR=$(cd "$(git rev-parse --git-dir)" && pwd -P)
GIT_COMMON=$(cd "$(git rev-parse --git-common-dir)" && pwd -P)
# GIT_DIR != GIT_COMMON  -> already inside a linked worktree
```

## Crew specifics

- `agents/dc-*.md` are Claude Code subagent definitions. On Codex, install the
  equivalents as role files under `~/.codex/agents/` and select them with
  `agent_type` on an isolated fork (`fork_turns: "none"`).
- The phase gate ships as a Claude Code `PreToolUse` hook and **does not run on
  Codex** — the relay's ordering becomes a discipline the conductor enforces by
  reading each phase's contract, not something the harness refuses to break.
- Per-role model tiers live in `.claude/roles/crew.md`; carry both `model` and
  `reasoning_effort` onto each spawn.
