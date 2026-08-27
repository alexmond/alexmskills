# alexmskills root demo — the progress-channel plugin, live.
# Regenerate with: vhs demo.tape
# Needs: vhs + ttyd + ffmpeg, and alexmond/skillsample checked out as a
# sibling of this repo (the demo stage the workload runs from).
# The hidden prelude uses a throwaway PROGRESS_HOME/PORT and seeds one run
# so the visible run shows a learned ETA and the forecast has history.

Output demo.gif

Set Shell bash
Set FontSize 16
Set Width 1200
Set Height 400
Set Padding 16
Set TypingSpeed 45ms

Hide
Type `export PROGRESS_HOME=$(mktemp -d) PROGRESS_PORT=7727`
Enter
Type `export PROGRESS_CLI="python3 $PWD/plugins/progress-channel/scripts/progress.py"`
Enter
Type `progress() { $PROGRESS_CLI "$@"; }`
Enter
Type `cd ../skillsample`
Enter
Type `TOTAL=40 DELAY=0.03 ./workloads/import-photos.sh >/dev/null 2>&1`
Enter
Sleep 8s
Type `clear`
Enter
Show

Type `# alexmskills · progress-channel — every long-running job, one visible channel`
Enter
Sleep 1.5s
Type `TOTAL=50 DELAY=0.12 ./workloads/import-photos.sh >/dev/null &`
Enter
Sleep 1s
Type `progress watch`
Enter
Sleep 14s
Ctrl+C
Sleep 500ms
Type `clear`
Enter
Type `progress forecast 'photo import'`
Enter
Sleep 4s

Hide
Type `kill $(curl -s 127.0.0.1:$PROGRESS_PORT/health | python3 -c 'import sys,json; print(json.load(sys.stdin)["pid"])') 2>/dev/null; true`
Enter
