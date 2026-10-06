# context-bar — the compaction advice at each level, rendered by the mod's own
# advise() over sample readings (see advice.mjs for why this is not a live
# recording). Regenerate from this directory: vhs advice.tape
# Writes advice.png; the .gif is a by-product and is not kept.

Output "advice.gif"

Set Shell bash
Set FontSize 16
Set Width 1200
Set Height 330
Set Padding 16

Hide
Type `clear && node --experimental-strip-types advice.mjs 2>/dev/null`
Enter
Sleep 2s
Show
Sleep 500ms
Screenshot "advice.png"
Sleep 500ms
