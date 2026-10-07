# usage-bar — the three colour states, rendered with the mod's own functions
# at sample percentages (see states.mjs). Not a live session: a recording can
# only show the state the account is in. Regenerate: vhs states.tape, then
# crop the still to the three rows:  ffmpeg -i states.png -vf crop=1200:192:0:0 out.png
Output "states.gif"
Set Shell bash
Set FontSize 16
Set Width 1500
Set Height 360
Set Padding 16
Hide
Type `clear && node --experimental-strip-types states.mjs 2>/dev/null`
Enter
Sleep 2s
Show
Sleep 500ms
Screenshot "states.png"
Sleep 500ms
