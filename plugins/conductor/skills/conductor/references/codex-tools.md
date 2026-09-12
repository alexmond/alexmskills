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

## Conductor specifics

The conductor is the role the **main session** adopts, so it is the one holding
these tools rather than being spawned by them.

- **Do not poll.** `wait_agent` wakes on mailbox activity; a completed lane's
  answer is pushed to you and arrives with your next turn. While you still have
  local work, do not wait at all.
- A lane that finished without reporting is found with `list_agents` after a
  wait stretch times out — that timeout is your cue to reconcile, not to
  shorten the next stretch.
- Relays go through `followup_task`; on Codex a spawned child can always be
  messaged again, so "dispatch a replacement" is never the recovery move.
- Verdict-reading, the four deviation shapes, and the parallelism ceiling are
  harness-independent — they are about lanes, not about tools.
