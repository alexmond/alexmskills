---
description: Open the mind-map canvas to sketch ideas, then compile them into a prompt
---

# `/mindmap-prompt:open`

Start the local canvas so the user can drop ideas and connect them.

## What to do

1. Resolve the plugin's `scripts/serve.py` (installed cache dir, else the dev checkout).
2. Run it in the background against the current repo:

   ```bash
   python3 <plugin>/scripts/serve.py --cwd "$PWD"
   ```

   Add `--map <name>` when the user names an existing map, and `--port N` if 8770 is taken.
3. Tell the user the URL in one line. That's it — don't recite the shortcuts, the
   page has a `?` button, and don't block waiting for them to finish.

## Notes

- Maps are written to `.claude/mindmap/<name>.canvas` in the current repo.
- The server binds `127.0.0.1` only and makes no external requests.
- When the user comes back and says they're done, run `/mindmap-prompt:compile`.
