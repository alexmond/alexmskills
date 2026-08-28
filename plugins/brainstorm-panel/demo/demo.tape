# brainstorm-panel demo — a REAL Claude Code session, recorded live with VHS.
# Regenerate from this directory: vhs demo.tape
# Needs: vhs + ttyd + ffmpeg, the brainstorm-panel plugin enabled (globally or
# via --plugin-dir), and alexmond/skillsample checked out as a sibling of the
# alexmskills repo (the demo stage the session runs in).
#
# The hidden prelude resets skillsample's panel state (so every take is an
# authentic first run), accepts the one-time trust dialog, pins a fast model,
# and wraps `claude` with --permission-mode acceptEdits (so the panel can write
# its registry/log without permission dialogs stalling the recording) and
# --disallowedTools AskUserQuestion (so choices arrive as text a scripted
# recording can answer, never as an interactive dialog). A local settings file
# pre-allows .claude/** access so the panel's registry/log writes (step 6)
# don't hit the .claude directory-access dialog mid-recording.
#
# Timing is nondeterministic — real model calls. Wait+Screen regexes gate each
# beat; if Claude's phrasing shifts, a take may need re-recording.

Output demo.gif

Set Shell bash
Set FontSize 16
Set Width 1200
Set Height 800
Set Padding 16
Set TypingSpeed 45ms
Set WaitTimeout 240s

Hide
Type `unset CLAUDECODE CLAUDE_CODE_CHILD_SESSION CLAUDE_CODE_ENTRYPOINT CLAUDE_CODE_SSE_PORT`
Enter
Type `export ANTHROPIC_MODEL=sonnet`
Enter
Type `claude() { command claude --permission-mode acceptEdits --allowedTools Bash --disallowedTools AskUserQuestion --strict-mcp-config "$@"; }`
Enter
Type `cd ../../../../skillsample && rm -rf .claude/roles .claude/brainstorm-panel && mkdir -p .claude/roles .claude/brainstorm-panel`
Enter
Type `printf '# Panel roles registry\n' > .claude/roles/panel.md && printf '# Panel log\n' > .claude/brainstorm-panel/log.md`
Enter
Type `printf '{"permissions":{"allow":["Read(%s/.claude/**)","Edit(%s/.claude/**)","Bash(mkdir:*)"]}}' "$PWD" "$PWD" > .claude/settings.local.json`
Enter
Type `command claude --permission-mode acceptEdits`
Enter
Sleep 10s
Enter
Sleep 5s
Type `/exit`
Enter
Sleep 3s
Type `clear`
Enter
Show

Type `# brainstorm-panel — real session: Claude assembles a panel, debates, decides`
Enter
Sleep 1.5s
Type `claude "/brainstorm-panel:brainstorm-panel pick this repo's second demo workload — decide only, don't build it. propose your panel, then wait for my go."`
Enter
Hide
Sleep 15s
Screenshot /tmp/bp_shot_postprompt.png
Wait+Screen@240s /dd, remove|onvene|swap/
Screenshot /tmp/bp_shot_gate.png
Show
Sleep 8s
Type `go`
Enter
Sleep 6s
Hide
Screenshot /tmp/bp_shot_go.png
Wait+Screen@600s /nresolved tension|hangelog/
Screenshot /tmp/bp_shot_final.png
Show
Sleep 8s
Type `so, one line — what won and why?`
Enter
Sleep 25s

Hide
Type `/exit`
Enter
Sleep 2s
