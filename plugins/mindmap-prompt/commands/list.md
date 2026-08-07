---
description: List the saved mind maps in this repo
---

# `/mindmap-prompt:list`

Show what maps exist so the user can pick one up again.

## What to do

1. List `.claude/mindmap/*.canvas` in the current repo.
2. For each, show the name, the goal, and the node count — cheap to get:

   ```bash
   python3 - <<'PY'
   import json, pathlib, re
   for p in sorted(pathlib.Path(".claude/mindmap").glob("*.canvas")):
       d = json.loads(p.read_text())
       nodes = [n for n in d.get("nodes", []) if n.get("type") == "text"]
       goal = next((n["text"] for n in nodes if re.match(r"\s*#goal\b", n.get("text", ""))), "(no goal)")
       print(f"{p.stem:24} {len(nodes):3} nodes  {goal.splitlines()[0][:60]}")
   PY
   ```

3. If there are none, say so and offer `/mindmap-prompt:open`.

Keep it to one line per map — this is a picker, not a report.
