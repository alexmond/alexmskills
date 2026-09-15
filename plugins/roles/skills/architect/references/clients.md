# Codex client path

Apply this section only in Codex. Keep every workflow phase, role definition,
quality gate, learning rule, and artifact from the main skill. The Claude Code
path remains unchanged.

- Resolve scripts and references relative to this installed skill/plugin; use
  `${PLUGIN_ROOT}` in Codex hooks. Never write learning state into the plugin cache.
- Read the consuming project's applicable `AGENTS.md` (and `AGENTS.override.md`
  where present). When a workflow says to update project instructions, update
  that file; keep `CLAUDE.md` for Claude. If they are symlinks to shared content,
  edit the shared content once. Do not create a competing instruction file.
- Keep existing `.claude/<plugin>/` workflow state shared across clients unless
  the client-specific instructions below specify a separate memory location.
- Map Read/Glob/Grep/Bash to available file/search/terminal tools, and Write/Edit
  to the available patch tool. Use actual tool schemas, not literal Claude tool names.
- Slash-command arguments mean the user's equivalent natural-language request
  on clients without that slash command. Preserve the command's complete procedure.
- Hook behavior requires installing the Codex plugin and reviewing/trusting its
  hooks with `/hooks`. A skill-only copy does not register hooks. Hook checks cover
  matched tool paths; shell-based edits and unexposed tool paths need the same
  checks in the workflow. Do not claim an instruction is a sandbox restriction.

The Codex SessionStart hook runs the existing registry initialization/audit.
Persona files, shared role state and all evolve/solo procedures remain intact.
