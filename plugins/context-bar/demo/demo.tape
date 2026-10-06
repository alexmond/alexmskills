# context-bar demo — a REAL Claude Code session, recorded live with VHS.
# The mod is loaded straight from this repo with --plugin-dir; one small
# prompt is sent so the bar has a turn to draw from, then /context-bar
# toggles it off and on.
#
# Regenerate from this directory: vhs demo.tape
# Needs: vhs + ttyd + ffmpeg, a Claude Code build with mods (function hooks),
# and alexmond/skillsample checked out as a sibling of the alexmskills repo.
# Writes demo.gif and demo.png (the still used by the docs and the README).

Output "demo.gif"

Set Shell bash
Set FontSize 16
Set Width 1200
Set Height 560
Set Padding 16
Set TypingSpeed 40ms
Set WaitTimeout 180s

Hide
Type `unset CLAUDECODE CLAUDE_CODE_CHILD_SESSION CLAUDE_CODE_ENTRYPOINT CLAUDE_CODE_SSE_PORT`
Enter
Type `export ANTHROPIC_MODEL=sonnet MOD="$PWD/.." SHOT="$PWD/demo.png"`
Enter
Type `cd ../../../../skillsample`
Enter
Type `clear`
Enter

Type `claude --plugin-dir "$MOD" --permission-mode acceptEdits --strict-mcp-config "read workloads/pipeline.sh and say what it does in two sentences"`
Enter
Wait+Screen@180s /\(\d+%\)/
Sleep 12s
Show
Sleep 3s
Screenshot "demo.png"
Sleep 2s
Type `/context-bar`
Sleep 1s
Enter
Sleep 4s
Type `/context-bar`
Sleep 1s
Enter
Sleep 5s

Hide
Type `/exit`
Enter
Sleep 2s
