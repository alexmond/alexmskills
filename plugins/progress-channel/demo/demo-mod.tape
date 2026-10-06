# progress-channel demo — the band mod (0.7.0), in a REAL Claude Code session.
# The plugin is loaded straight from this repo with --plugin-dir. This session
# has no status line, so the mod's `auto` mode draws the jobs above the prompt:
# the pipeline and its current stage, nested.
#
# Regenerate from this directory: vhs demo-mod.tape
# Needs: vhs + ttyd + ffmpeg, a Claude Code build with mods (function hooks),
# and alexmond/skillsample checked out as a sibling of the alexmskills repo.
# Writes demo-mod.gif and demo-mod.png. The hidden prelude uses a throwaway
# PROGRESS_HOME/PORT and seeds one identical run, so the visible run shows
# learned time-left.

Output "demo-mod.gif"

Set Shell bash
Set FontSize 16
Set Width 1200
Set Height 520
Set Padding 16
Set TypingSpeed 40ms
Set WaitTimeout 240s

Hide
Type `unset CLAUDECODE CLAUDE_CODE_CHILD_SESSION CLAUDE_CODE_ENTRYPOINT CLAUDE_CODE_SSE_PORT`
Enter
Type `export ANTHROPIC_MODEL=sonnet MOD="$PWD/.."`
Enter
Type `export PROGRESS_HOME=$(mktemp -d) PROGRESS_PORT=7741`
Enter
Type `export PROGRESS_CLI="python3 $PWD/../scripts/progress.py"`
Enter
Type `cd ../../../../skillsample`
Enter
Type `DELAY=0.6 ./workloads/pipeline.sh >/dev/null 2>&1`
Enter
Sleep 40s
Type `clear`
Enter

Type `claude --plugin-dir "$MOD" --settings '{"statusLine":{"type":"command","command":"true"}}' --permission-mode acceptEdits --allowedTools Bash --disallowedTools AskUserQuestion --strict-mcp-config "run the release pipeline: DELAY=0.6 ./workloads/pipeline.sh — start it right away, exactly as-is (it registers itself on the progress channel, so don't wrap it or add any tracking). don't tail or narrate the output. when it finishes, one line on how it went."`
Enter
Wait+Screen@120s /↳ /
Show
Sleep 6s
Screenshot "demo-mod.png"
Sleep 22s
Wait+Screen@120s /❯/
Sleep 3s

Hide
Type `/exit`
Enter
Sleep 2s
Type `kill $(curl -s 127.0.0.1:$PROGRESS_PORT/health | python3 -c 'import sys,json; print(json.load(sys.stdin)["pid"])') 2>/dev/null; true`
Enter
Sleep 1s
