---
description: Compile a saved mind map into an organized prompt and act on it
---

# `/mindmap-prompt:compile`

Turn a `.canvas` map into an organized Markdown prompt — then **do the work it
describes**. The compiled prompt is the user's actual request, not a report to
hand back.

## What to do

1. Pick the map: the name in `$ARGUMENTS`, else the only file in
   `.claude/mindmap/`, else ask which one.
2. Compile it:

   ```bash
   python3 <plugin>/scripts/mindmap.py compile .claude/mindmap/<name>.canvas
   ```

3. **Read the output and treat it as the prompt.** Plan and execute it the way
   you would any request of that size.
4. Surface any warnings in one line first — especially "not connected to the
   goal", because that is content the user wrote that did **not** reach the
   prompt. Offer `--include-orphans` if it looks unintentional.
5. If compilation fails, show the errors plainly (usually: no `#goal` node, or
   more than one) and offer to reopen the canvas.

## Flags

- `--include-orphans` — keep unconnected nodes under `## Unsorted notes`.
- `-o <file>` — write the prompt to a file instead of stdout.
