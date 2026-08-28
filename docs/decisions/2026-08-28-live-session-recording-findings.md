# Recording a real Claude Code session with VHS — findings

**Date:** 2026-08-28 · **Source:** the brainstorm-panel demo (`plugins/brainstorm-panel/demo/`),
which took **12 takes**. This is the playbook for the next live-session tape
(prompt-coach, dev-crew, …) so it doesn't re-earn these lessons.

## The one-line summary

**Interactivity, not timing, is what breaks scripted recordings.** Model latency is
solved by `Wait+Screen` regexes; every actual failure was a UI element a script
can't answer — a skill-picker roulette, a selection dialog, or a permission gate.

## Failure catalog (what each take taught)

| # | Failure | Root cause | Fix |
|---|---|---|---|
| 1 | Roster gate skipped | Prompt pre-pinned seats/rounds → skill treated scope as pre-approved | Don't pre-pin what the beat is supposed to show |
| 2, 5 | Timeout at a selection dialog | Conductor used **AskUserQuestion** for the gate / a clarifying question | `--disallowedTools AskUserQuestion` |
| 3, 6, 7 | Timeout, empty transcript, "← 2 agents" | **superpowers:brainstorming hijacked the word "brainstorm"** — a globally-installed skill shadowed the plugin skill | Invoke by **slash form** (`/brainstorm-panel:brainstorm-panel …`); CLAUDE.md disambiguation as backup |
| 4 | Instant parse error | VHS `Screenshot` path parser chokes on **hyphens** in the path | Hyphen-free paths (`/tmp/bp_shot_x.png`) |
| 8 | Timeout at "Run shell command" dialog | `--permission-mode acceptEdits` covers edits, **not Bash** | `--allowedTools Bash` |
| 9 | Timeout at ".claude is a sensitive file" dialog | Panel step-6 state writes hit the **`.claude` directory gate**; also: unconstrained "pick X" scope-crept into *building* X (13-min run) | Pre-create `.claude` dirs; **"decide only, don't build it"** in the prompt |
| 10 | Dialog over the last 9s | Conductor ran `mkdir` on `.claude` paths — sensitive-path gate again | Pre-`mkdir` the dirs in the prelude |
| 11 | "Do you want to create panel.md?" over the ending | The **own-settings guard** on creating files under `.claude` — allow-rules deliberately can't pre-approve it | Stage-repo CLAUDE.md: *don't persist panel state here* (it's gitignored + reset per take); stub files pre-seeded as defense |
| 12 | ✅ clean | — | — |

## The hardened invocation (copy this)

Hidden prelude, in order:

```bash
unset CLAUDECODE CLAUDE_CODE_CHILD_SESSION CLAUDE_CODE_ENTRYPOINT CLAUDE_CODE_SSE_PORT
export ANTHROPIC_MODEL=sonnet
claude() { command claude --permission-mode acceptEdits --allowedTools Bash \
  --disallowedTools AskUserQuestion --strict-mcp-config "$@"; }
cd <stage-repo> && rm -rf <mutable .claude state> && mkdir -p <state dirs> && <seed stubs>
printf '{"permissions":{"allow":["Read(%s/.claude/**)","Edit(%s/.claude/**)","Bash(mkdir:*)"]}}' \
  "$PWD" "$PWD" > .claude/settings.local.json
command claude --permission-mode acceptEdits   # accept one-time trust dialog; /exit
```

Why each flag:

- **Unset the env markers** — the VHS shell inherits them from the recording
  session; claude then runs in child-session mode: a warning banner in every
  frame and **no transcript saved** (which you need for forensics).
- **`--strict-mcp-config`** — kills the "N MCP servers need authentication"
  banner wart.
- **Slash-form invocation** — skill triggering by phrase is a roulette when any
  other installed skill claims the same word. The slash form is also the
  documented "Try it" line, so it doubles as teaching.
- **Stage-repo `CLAUDE.md`** carries: recording etiquette (text choices only,
  wait for a typed reply), small-panel default, the trigger-word
  disambiguation, and the no-state-persistence rule. Prose steering alone did
  NOT beat AskUserQuestion's pull — the flag is what works; CLAUDE.md is
  belt-and-suspenders and makes the conductor *explain the constraint on
  camera*, which reads great.

## Beats and timing

- Gate every beat with `Wait+Screen@<timeout> /regex/`. Choose regex words that
  **cannot appear in the typed prompt** (the prompt stays on screen — a word it
  contains matches instantly).
- Typing into a still-running turn is safe: Claude Code queues the message and
  delivers at turn end. Dialogs are the only true blockers.
- A follow-up coda ("so, one line — what won and why?") makes the final frame
  carry the verdict — the decision headline itself scrolls off-screen in a long
  final message.
- `Set Height 800` for TUI content; `Hide` the minutes of wall-clock between
  beats. ~26s visible from a ~6-min session.

## Diagnosis toolkit (in order of leverage)

1. **Session transcripts** — `~/.claude/projects/<stage-repo-slug>/*.jsonl`; jq
   the `tool_use` names and last assistant text. This is what found the
   superpowers hijack. (Requires the env-marker unset, else nothing is saved.)
2. **VHS failure dump** — prints only the final screen; often just the status
   bar. Better than nothing, far worse than the transcript.
3. **VHS `Screenshot` checkpoints** — written **only on successful runs**
   (buffered); useless for failure diagnosis, good for verifying a green take.
4. **tmux probe** — drive the identical invocation via `tmux new-session` +
   `capture-pane` to watch the real screen. Note: the harness classifier blocks
   `send-keys` into a claude TUI; launch the session with the prompt as an
   argument instead and observe read-only.
5. **Frame review** — `ffmpeg -vf fps=1` + read the PNGs. Catches layout warts
   (dead space, banners) that text dumps miss.

## Size

64-color palette re-encode (`ffmpeg palettegen max_colors=64` + `paletteuse
dither=none`) cut 6.2 MB → 4.8 MB with text pixel-identical to the eye.
gifsicle isn't installed here. Target <5 MB, hard GitHub cap 10 MB.

## Open items for the next tape

- The whole prelude is copy-paste portable except the `cd ../../../../skillsample`
  sibling-path assumption — keep it, it's the convention from the root tape.
- If a future skill's flow *requires* a dialog beat, VHS has no conditionals —
  redesign the beat, don't try to script the dialog.
- Take cost is real (a full panel run per take): fix ONE variable per take and
  read the transcript before re-recording.
