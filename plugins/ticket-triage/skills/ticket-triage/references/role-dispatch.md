# Role-dispatch discipline

Applies when the shared `roles` substrate is present (`.claude/roles/<role>.md`,
seeded by the `roles` plugin). Without it, dispatch generic agents with the same
briefs — everything else in the skill still holds.

- **The brief tells the agent to READ the role file** (and to seed it from the
  plugin if absent) — never merely name the role at it. Naming a role in a brief
  buys nothing; the file is where the repo's accumulated lessons live.
- **Seed the registry on main BEFORE dispatching** a round that needs roles
  `.claude/roles/` does not yet hold. Otherwise every agent *creates* the file
  independently and they collide on merge — N agents, N versions of one file,
  and the merge resolution silently picks a winner.
- **One role file, one writer per round.** Name the owner in each brief; the
  others *report* their learning line in their final message so the conductor
  applies it. Two lanes appending to one role file is the same collision as
  above, arriving later.
- **Role files are repo state, so learnings belong in the PR.** A worktree agent
  that appends a learning and never commits it has thrown it away — the worktree
  is deleted after the merge.
- **Minting a new role needs a stated gap** — one sentence naming work no
  existing role covers — plus a line in the report saying a role was minted and
  why. Without the gap sentence, roles proliferate into near-duplicates and the
  learning loop fragments across them.
