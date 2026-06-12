# senior-prompts (beta)

A small, **self-improving** prompt library that reframes tasks as "think like a senior engineer X"
instructions, each packaged as an explicit, user-invoked skill. Call them by short reference — they
don't auto-trigger.

| Skill | Invoke | Purpose |
| --- | --- | --- |
| Build app from scratch | `/senior-prompts:build-app` | Architecture-first, production-ready MVP |
| Understand & refactor | `/senior-prompts:understand-refactor` | Map an unfamiliar codebase, then improve it safely |
| Root-cause debug | `/senior-prompts:debug-root-cause` | Production debugging to the true root cause |
| System design + build | `/senior-prompts:system-design` | Scalable design, then minimal production code |
| Optimize performance | `/senior-prompts:optimize-perf` | Find bottlenecks; improve speed/memory/scale |
| Clean architecture | `/senior-prompts:clean-arch` | Separate concerns, reduce coupling, same behavior |

Each skill takes a free-text argument (the target/file/feature).

## Self-improving (init · capture · compress)

The plugin ships a SessionStart hook (`hooks/hooks.json` → `scripts/compress-learnings.py`) that:

- **inits on first run** — creates `.claude/senior-prompts/learnings.md` in the repo;
- each skill **reads** that log before working and **captures** a one-line lesson when a run surfaces
  something durable (a multi-cycle fix, a stack gotcha, a stated preference);
- **compresses** — when the log grows, the hook recommends compaction (merge duplicates, drop the
  now-obvious) so it stays lean.

## Trimmed on purpose

Two prompts from the original set were dropped because this marketplace already has stronger tools:

- **Multi-agent workflow** → use **`dev-crew`** (real subagents, model tiers, gates, learning loop)
  or **`brainstorm-panel`** (multi-lens ideation).
- **UI component builder** → use the **`frontend-design`** plugin.

> Adapted and rewritten into skill form from a prompt thread by **@nahidulislam404** on X. The wording
> here is generalized and structured for reuse; the original framing inspired the set.

This is a **beta** plugin. Promote it to the stable catalog with `make promote PLUGIN=senior-prompts`.
