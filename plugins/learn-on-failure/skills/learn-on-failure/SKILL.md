---
name: learn-on-failure
description: >
  Save a learning to project memory. Invoke automatically (without the user asking) whenever
  a task required more than one fix cycle to resolve — e.g. a test failed and needed a
  second attempt, a compile error required a correction, an API behaved unexpectedly, or
  an assumption proved wrong mid-task. Also invoke when the user explicitly asks to
  remember something. Do NOT invoke for routine single-pass work.
argument-hint: "[topic] [what you learned]"
---

## Save a learning to project memory

$ARGUMENTS

### Locate the project memory directory

Claude Code keeps per-project memory at `~/.claude/projects/<project-slug>/memory/`, where
`<project-slug>` is derived from the current project's absolute path. Do **not** hardcode a path —
the active project's memory directory is provided in the session's memory/system context. Use that
path. Within it:

- `MEMORY.md` is the index.
- Topic files (e.g. `dependencies.md`, `testing.md`, `debugging.md`) hold detailed, subject-specific notes.

If the memory directory or `MEMORY.md` does not yet exist, create them.

### Determine the learning

If triggered **automatically** (multi-cycle resolution), synthesise the learning from the conversation:

- What was the root cause of the extra cycle(s)?
- What assumption or gap in knowledge caused the first attempt to fail?
- What is the correct approach / API / behaviour?
- What should be checked first next time to avoid the same detour?

If triggered **by the user**, record exactly what they stated in `$ARGUMENTS`.

### Steps

1. Read the current `MEMORY.md` index in the project's memory directory.

2. Check whether a relevant topic file already exists in that same directory. If so, read it too.

3. Decide where to write:
    - Short, self-contained insight that fits an existing `MEMORY.md` section → add it there (keep file ≤ 200 lines).
    - Detailed or topic-specific learning → append to or create a dedicated topic file, then add/update a one-line
      reference in `MEMORY.md`.

4. Write in concise, actionable form:
    - Bullet points, not prose.
    - Lead with *what to do / what to check*, follow with *why*.
    - If it supersedes an existing note, update or remove the old one.

5. Confirm to the user what was saved and where (one line is enough).

### What to save

- Root causes of multi-cycle failures and the correct fix
- Non-obvious library behaviours or API quirks discovered during the task
- Version constraints and compatibility issues (e.g. BCrypt prefix `$2y$` vs `$2a$`)
- Architectural decisions and their rationale
- Workflow or tool preferences the user has stated
- Patterns confirmed to work that aren't obvious from the code

### What NOT to save

- Routine outcomes that worked first time
- Temporary task state or in-progress work
- Anything already covered verbatim in the project's `CLAUDE.md`
- Guesses or conclusions that were not verified by a passing test or explicit confirmation
