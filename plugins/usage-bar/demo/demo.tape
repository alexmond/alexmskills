# usage-bar demo — a REAL Claude Code session, recorded live with VHS.
# The mod is loaded straight from this repo with --plugin-dir; one small
# prompt is sent so there is an API response to read the limits from, then
# /usage-bar toggles it off and on.
#
# Regenerate from this directory: vhs demo.tape
# Needs: vhs + ttyd + ffmpeg, a Claude Code build with mods (function hooks),
# and alexmond/skillsample checked out as a sibling of the alexmskills repo.
# Writes demo.gif and demo.png. The bar shows the recording account's real
# limits, so it is green unless that account is near one — states.tape
# renders all three colours.

Output "demo.gif"

Set Shell bash
Set FontSize 16
Set Width 1200
Set Height 480
Set Padding 16
Set TypingSpeed 40ms
Set WaitTimeout 180s

Hide
Type `unset CLAUDECODE CLAUDE_CODE_CHILD_SESSION CLAUDE_CODE_ENTRYPOINT CLAUDE_CODE_SSE_PORT`
Enter
Type `export ANTHROPIC_MODEL=sonnet MOD="$PWD/.."`
Enter
Type `cd ../../../../skillsample`
Enter
Type `clear`
Enter

Type `claude --plugin-dir "$MOD" --permission-mode acceptEdits --strict-mcp-config "in one sentence: what is in the workloads folder?"`
Enter
Wait+Screen@180s /5h [█░]/
Sleep 12s
Show
Sleep 3s
Screenshot "demo.png"
Sleep 2s
Type `/usage-bar`
Sleep 1s
Enter
Sleep 4s
Type `/usage-bar`
Sleep 1s
Enter
Sleep 5s

Hide
Type `/exit`
Enter
Sleep 2s
