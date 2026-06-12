# clean-arch

## Charter
Restructure code into clean architecture like a senior engineer — separate concerns, raise modularity, reduce coupling; structure improves while behavior stays the same.

## When to use
- Code where business logic, I/O, and presentation are tangled together
- Modules with high coupling or unclear layer boundaries that resist change
- Requests to "restructure," "modularize," or apply clean/hexagonal/layered architecture
- Defining target layouts and dependency direction before a larger rebuild
- Deciding how much architectural separation a codebase's complexity actually justifies

## Body
Think like a senior engineer converting code to clean architecture. Separate concerns, increase
modularity, reduce coupling — **behavior unchanged, structure improved**.

1. **New folder/module structure** — the target layout and the layer boundaries.
2. **Architecture description** — responsibilities per layer and the dependency direction
   (dependencies point inward).
3. **Refactored code** — move logic into the new structure; keep public behavior identical.

Don't over-engineer: apply only the separation the code's actual complexity justifies.

## Learnings (core)
<!-- Context-independent lessons only. Entries arrive by graduation (user-gated), never direct append. -->

## Learnings (solo)
<!-- Appended by solo runs. One line each: `- YYYY-MM-DD — lesson` -->
