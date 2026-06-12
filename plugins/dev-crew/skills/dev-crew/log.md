# dev-crew run log

Append-only. The learning loop reads this to graduate lineups, re-tier models,
and detect missing roles. One entry per run. Newest at the bottom.

## Entry schema

```
## <run-id>  <yyyy-mm-dd>  <repo>
- category: <feature|bugfix|refactor|schema-change|perf|release|infra|...>
- task: <one line>
- roster: architect(opus) -> dev(sonnet) -> qa(sonnet) -> deployer(haiku)
- mode: <autopilot | checkpoint | co-drive>
- outcome: <shipped | blocked-at-<gate> | abandoned>
- per-role:
  - architect: <result, notable decisions>
  - dev: <result, scope flags>
  - qa: <pass/fail per criterion; defects caught + where introduced>
  - deployer: <dry checks; commands staged; go given by user? y/n>
- gate-events: <qa loops, deploy holds, escalations>
- steering: <mid-run injections: what you changed, which phase, and why — the learning loop reads this>
- model-fit: <any role over/under-powered for this run>
- missing-role: <recurring failure class with no owner, if any>
- graduated: <lineup/re-tier/new-role changes written back this run, if any>
```

---

<!-- entries below -->
