# progress-channel demo — a REAL Claude Code session, recorded live with VHS.
# A simulated Maven reactor build runs as a Claude tool call; the job registers
# itself on the progress channel and the session's status line shows the live
# bar with a learned ETA — no narration, no re-polling.
#
# Regenerate from this directory: vhs demo-claude.tape
# Needs: vhs + ttyd + ffmpeg, the progress-channel plugin installed (its
# status-line renderer appended to the user's status line), and
# alexmond/skillsample checked out as a sibling of the alexmskills repo.
#
# Recording-hardened invocation (see the brainstorm-panel demo tape and
# docs/decisions/2026-08-28-live-session-recording-findings.md): child-session
# env unset, --allowedTools Bash (no permission dialog mid-build),
# --disallowedTools AskUserQuestion (dialogs can't be driven by a script),
# trust dialog pre-accepted in the hidden prelude. A throwaway
# PROGRESS_HOME/PORT isolates the take from the machine's live daemon; one
# hidden seed run gives the visible build a learned ETA.

Output demo-claude.gif

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
Type `export PROGRESS_HOME=$(mktemp -d) PROGRESS_PORT=7737`
Enter
Type `export PROGRESS_CLI="python3 $PWD/../scripts/progress.py"`
Enter
Type `claude() { command claude --permission-mode acceptEdits --allowedTools Bash --disallowedTools AskUserQuestion --strict-mcp-config "$@"; }`
Enter
Type `cd ../../../../skillsample`
Enter
Type `DELAY=1.2 ./workloads/maven-build.sh >/dev/null 2>&1`
Enter
Sleep 35s
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

Type `# progress-channel — real session: the build reports itself on the status line`
Enter
Sleep 1.5s
Type `claude "run the maven build workload: DELAY=1.2 ./workloads/maven-build.sh — start it right away, exactly as-is (it registers itself on the progress channel, so don't wrap it or add any tracking). don't tail or narrate the output. when it finishes, one line on how it went."`
Enter
Hide
Sleep 5s
Screenshot "/tmp/pc_shot_postprompt.png"
Wait+Screen@240s /░░░/
Show
Sleep 14s
Screenshot "/tmp/pc_shot_statusline.png"
Sleep 16s
Hide
Wait+Screen@240s /succe|Succe|assed|reen|SUCCESS/
Screenshot "/tmp/pc_shot_final.png"
Show
Sleep 8s

Hide
Type `/exit`
Enter
Sleep 2s
