# progress-channel demo — sub-jobs (0.6.0): a pipeline and its current step.
# Regenerate from this directory: vhs demo-subjobs.tape
# Needs: vhs + ttyd + ffmpeg, and alexmond/skillsample checked out as a
# sibling of the alexmskills repo (the demo stage the workload runs from).
#
# The workload is skillsample's workloads/pipeline.sh: it registers once and
# exports PROGRESS_PARENT, so every stage nests itself — including
# maven-build.sh, run as an unmodified sub-script. The hidden prelude uses a
# throwaway PROGRESS_HOME/PORT and seeds one identical run, so the visible run
# shows learned time-left on every row, parent included.

Output "demo-subjobs.gif"

Set Shell bash
Set FontSize 16
Set Width 1200
Set Height 420
Set Padding 16
Set TypingSpeed 40ms

Hide
Type `export PROGRESS_HOME=$(mktemp -d) PROGRESS_PORT=7728 CLAUDE_CODE_SESSION_ID=demo-subjobs`
Enter
Type `export PROGRESS_CLI="python3 $PWD/../scripts/progress.py"`
Enter
Type `SL="python3 $PWD/../scripts/statusline.py"`
Enter
Type `progress() { $PROGRESS_CLI "$@"; }`
Enter
Type `statusline() { while sleep 1; do o=$($SL </dev/null); clear; printf '# pipeline.sh exports PROGRESS_PARENT, so every stage nests itself.\n# The Claude Code status line, live:\n\n%s\n' "$o"; done; }`
Enter
Type `cd ../../../../skillsample`
Enter
Type `DELAY=0.3 ./workloads/pipeline.sh >/dev/null 2>&1`
Enter
Sleep 34s
Type `clear`
Enter
Type `(DELAY=0.3 ./workloads/pipeline.sh >/dev/null &)`
Enter
Type `statusline`
Enter
Sleep 1500ms
Show

Sleep 29s
Hide
Ctrl+C
Sleep 300ms
Type `clear`
Enter
Sleep 300ms
Show
Type `progress list | head -5`
Enter
Sleep 4s

Hide
Type `kill $(curl -s 127.0.0.1:$PROGRESS_PORT/health | python3 -c 'import sys,json; print(json.load(sys.stdin)["pid"])') 2>/dev/null; true`
Enter
