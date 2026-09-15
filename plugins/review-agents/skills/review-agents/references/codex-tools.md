# Agent dispatch on Codex

Keep all roles, rounds, handoffs, escalation rules and learning from SKILL.md.
Inspect the live tool schema before dispatching; Codex clients expose different
agent interfaces. Enable multi-agent if supported and needed. If no agent tools
are available, report that limitation and run sequentially without claiming
independent or parallel reviews.

For a shipped `agents/<role>.md`, read the entire file. Pass its complete body,
the task brief, project context, output contract, and tool restrictions in the
child's initial instructions. Include the role name (for example `dc-dev`) in
both its task name and message so the phase gate can identify it. Claude agent
Markdown is not automatically a registered Codex agent type. Use a custom
`agent_type` only if an equivalent is already registered in that client.

Use `spawn_agent` (or the live equivalent), one child per independent role.
Use a clean context when the tool supports it and supply all needed material.
Collect returned child results via the available wait/result mechanism; do not
read Claude transcript files. Respect the runtime's wait limit and keep the user
updated. Send corrections using the exposed message/follow-up tool, distinguishing
message delivery from restarting an idle child. Close workers when supported.

Map Haiku/Sonnet/Opus/Fable preferences to available models with equivalent roles
(fast routine work / balanced implementation / strongest review). Never send
Anthropic model names to Codex. Inherit the current model unless the user or role
instructions authorize a supported override. Where model and reasoning effort
are supported, specify both for an override; otherwise report the limitation.

A prompt's tool restrictions remain instructions unless the runtime exposes a
matching enforceable tool or sandbox policy. Preserve no-source-edit rules for
reviewers while allowing their documented build/test commands. Never grant extra
permissions to emulate Claude tool metadata; report any enforcement difference.
