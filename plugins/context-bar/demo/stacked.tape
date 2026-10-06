# Both mods at once — a REAL Claude Code session, recorded live with VHS.
# context-bar and usage-bar are loaded together with two --plugin-dir flags.
# A band holds ONE tree, so each mod draws its own rows and then whatever the
# rest of the chain draws; this take is the check that neither hides the other.
#
# Regenerate from this directory: vhs demo.tape
# Needs: vhs + ttyd + ffmpeg, a Claude Code build with mods (function hooks),
# and alexmond/skillsample checked out as a sibling of the alexmskills repo.
# Writes stacked.gif and stacked.png.

Output "stacked.gif"

Set Shell bash
Set FontSize 16
Set Width 1200
Set Height 600
Set Padding 16
Set TypingSpeed 40ms
Set WaitTimeout 180s

Hide
Type `unset CLAUDECODE CLAUDE_CODE_CHILD_SESSION CLAUDE_CODE_ENTRYPOINT CLAUDE_CODE_SSE_PORT`
Enter
Type `export ANTHROPIC_MODEL=sonnet MOD="$PWD/.." MOD2="$PWD/../../usage-bar"`
Enter
Type `cd ../../../../skillsample`
Enter
Type `clear`
Enter

Type `claude --plugin-dir "$MOD" --plugin-dir "$MOD2" --permission-mode acceptEdits --strict-mcp-config "read workloads/pipeline.sh and say what it does in two sentences"`
Enter
Wait+Screen@180s /\(\d+%\)/
Sleep 12s
Show
Sleep 3s
Screenshot "stacked.png"
Sleep 4s

Hide
Type `/exit`
Enter
Sleep 2s
