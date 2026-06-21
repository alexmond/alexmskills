<!-- SHIPPED SEED — read-only when installed as a plugin. The live, append-only log
     lives at <repo>/.claude/research-sweep/log.md; the synthesizer copies this schema
     there on first run. Never write to this installed copy. -->
# research-sweep run log

Append-only. The learning loop reads this to graduate stable coverage roles,
demote thin angles, retire dead ones, and lift cross-corpus patterns into the
repo's `## Research sweep` CLAUDE.md block. One entry per sweep. Newest at the
bottom.

## Entry schema

```
## <run-id>  <yyyy-mm-dd>  <repo>
- question: <one-line research question>
- corpus: <the information space — "open-source vector DBs", "ICML 2024 papers", ...>
- roster: container-scout, timeline-scout, citation-graph-scout(probationary) + verifier(skeptic) + synthesizer
- partition: <axis used — by-language / by-era / by-registry / ...>
- schema: <top-level key + required fields, e.g. `databases: {id,name,language,license,source_url}`>
- per-role:
  - <role>: volume=<n> (target <m>), thin=<no | slice-thin | agent-thin>, notes=<sources hit, gaps>
  - ...
- verifier:
  - sample: <n entries / <pct>%>
  - fabrications: <count + class — fake URLs / wrong dates / invented IDs>
  - duplicates: <count + which seam>
  - gaps: <obvious missing entries the sweep should have caught>
  - verdict: <accepted | accepted-with-cuts | re-run-required>
- thin: <any role that came back thin + diagnosis (slice-thin: corpus genuinely sparse → merge/shrink; agent-thin: prompt/web/angle → re-run/re-role) + action taken>
- dedup-hotspots: <which seams collided + the ID rule that prevented it next time>
- source-trust: <authoritative sources for this corpus; sources caught fabricating>
- steering: <what the user changed at the roster gate — added angle / cut angle / retuned slice — and why>
- outcome: <committed-at <path> | partial | abandoned>
- graduated: <row promotions (probationary → stable), demotions, retirements, CLAUDE.md block updates written back this run, if any>
```

---

<!-- entries below -->
