# research-sweep run log

Append-only. The learning loop reads this to graduate stable coverage roles,
demote thin angles, retire dead ones, and lift cross-corpus patterns into the
repo's `## Research sweep` CLAUDE.md block. One entry per sweep. Newest at the
bottom. (Schema: see the shipped seed in the research-sweep plugin.)

---

<!-- entries below -->

## demo-promo-2026-08-27  2026-08-27  alexmskills
- question: what demo, demo-recording, and promotion practices do third-party Claude Code skill repos use — to adopt a format for alexmskills
- corpus: Claude Code skill/plugin collections + marketplaces, demo-recording tooling ecosystem, discovery/announcement channels
- roster: container-scout + demo-tooling-scout(probationary, minted) + promotion-scout(probationary, minted) + verifier(skeptic) + synthesizer
- partition: by-aspect — repo presentation / recording mechanics / discovery channels (disjoint by explicit do-NOT-cover fences in each brief)
- schema: `findings: {id,practice,repo_or_source,url,evidence}` + optional `{prevalence,applicability}`
- per-role:
  - container-scout: volume=17 (target 14), thin=no, notes=8+ collections incl. anthropics/skills, obra/superpowers, wshobson/agents, davila7, awesome lists, skills.sh
  - demo-tooling-scout: volume=18 (target 14), thin=no, notes=VHS/asciinema/agg ecosystems, GitHub media limits from primary docs, .tape code-search cohort
  - promotion-scout: volume=17 (target 14), thin=no, notes=44 tool calls — heaviest slice; Reddit needed a headless browser (direct fetch blocked)
- verifier:
  - sample: 12 findings / 23%
  - fabrications: 0 — all URLs resolved; exact figures re-confirmed to the digit; 1 misattributed quote (repoclip.io page lacks the quoted npm/IDE claim), 2 Reddit scores unverifiable (Reddit blocks fetching)
  - duplicates: 0 across seams — 3 agents touched anthropics/skills + obra/superpowers with consistent, non-overlapping findings
  - gaps: X build-in-public threads, YouTube/video creators, Claude Developers Discord, newsletters (Simon Willison/TLDR) + Product Hunt
  - verdict: accepted (treat Reddit scores + repoclip quote as approximate, not load-bearing)
- thin: none
- dedup-hotspots: none — the do-NOT-cover fence per brief prevented seam overlap; keep the fence wording
- source-trust: primary docs (docs.github.com, code.claude.com) and GitHub repo pages fully reliable; Reddit unfetchable directly (headless browser or HN/press mirrors needed); blog-via-search quotes must be re-checked on the cited page before quoting
- steering: roster approved unchanged at the gate
- outcome: committed-at .claude/research-sweep/2026-08-27-demo-promo-findings.yaml; report at docs/decisions/2026-08-27-demo-promotion-practices.md
- graduated: minted demo-tooling-scout + promotion-scout as probationary (1 useful run each); verifier row gains the Reddit-unfetchable + quote-misattribution patterns

## claude-md-practices-2026-08-28  2026-08-28  alexmskills
- question: CLAUDE.md best practices — content, content separation, internal structure — to ground evolving-claude-md's structure-evolution capability (#37/#41/#42)
- corpus: official Anthropic docs + AGENTS.md spec / real committed CLAUDE.md-AGENTS.md files in notable repos / practitioner blogs, HN-Reddit threads, measured studies
- roster: source-scout(stable) + container-scout(stable) + practitioner-scout(probationary, minted) + verifier(skeptic) + synthesizer
- partition: by content kind — prescribed (official docs) / shipped (repo files) / debated (practitioner prose), disjoint by do-NOT-cover fences
- schema: `findings: {id,claim,evidence,source_url,confidence,category}` with category ∈ content|separation|structure|size|evolution|anti-pattern
- per-role:
  - source-scout: volume=40 (target 15), thin=no, notes=memory/best-practices/features-overview/large-codebases pages + agents.md spec; near-verbatim quote capture
  - container-scout: volume=30 (target 15), thin=no, notes=~40 files fetched raw; byte-exact sizes; found the symlink-to-AGENTS.md dominant pattern + the OpenHands accretion anti-pattern
  - practitioner-scout: volume=26 (target 15), thin=no, notes=found 3 MEASURED sources (arXiv 2605.10039, GitHub 2500-repo analysis, Schmid-cited studies) — the highest-value slice
- verifier:
  - sample: 12 findings / 12.5%, stratified by scout, weighted to load-bearing numbers/quotes
  - fabrications: 0; misattributions: 0; every checked number exact to the byte; 3 cosmetic wording corrections applied to the YAML
  - duplicates: 0 across seams; cross-scout corroboration noted (imports-load-at-launch confirmed independently by og- and cp-)
  - gaps: none — all 6 categories populated (content 17, separation 21, structure 20, size 11, evolution 15, anti-pattern 12)
  - verdict: accepted with corrections (applied)
- thin: none
- dedup-hotspots: none — the by-content-kind partition (prescribed/shipped/debated) produces zero natural overlap; reuse it for any docs-vs-practice survey
- source-trust: code.claude.com docs quote-stable; raw.githubusercontent.com byte-exact for repo claims; genuine source seams exist (size guidance 200 vs 300 vs measured-null; /init vs never-auto-generate) — report seams as findings, never reconcile them silently
- steering: roster approved via "implement whole scope"; no gate edits
- outcome: committed-at .claude/research-sweep/2026-08-28-claude-md-practices-findings.yaml; shipped synthesis at plugins/evolving-claude-md/references/claude-md-best-practices.md (in-plugin rulebook — first sweep whose deliverable ships inside a plugin)
- graduated: practitioner-scout minted probationary (1 useful run); verifier row gains the raw-github-byte-exact pattern

## conductor-landscape-2026-09-12  2026-09-12  alexmskills
- question: conductor-type skills/agents/roles across the coding-agent ecosystem, to position plugins/conductor 0.1.0
- corpus: Claude Code marketplaces/collections / framework+product official docs / practitioner lore + measured studies
- roster: container-scout(stable) + entity-scout(stable, first use this repo) + practitioner-scout(probationary, 2nd run) + verifier(skeptic) + synthesizer
- partition: by artifact locus — shipped CC ecosystem / framework-native roles / practice+measurement, do-NOT-cover fences
- schema: findings{id,name,kind,origin,source_url,supervises,drift_detection,verification,parallelism,learning_loop,confidence}
- per-role:
  - container-scout: volume=17 (target 14), thin=no, notes=marketplace long tail found; 2 thin-but-real plugin entries flagged marginal by verifier
  - entity-scout: volume=18 (target 12), thin=no, notes=official docs only; adk.dev verified as REAL official Google domain (verifier initially suspected fabrication)
  - practitioner-scout: volume=14 (target 12), thin=no, notes=6 MEASURED sources (MAST, Agent-as-a-Judge, Google/MIT scaling, METR RCT, AgenticFlict, Anthropic MARS) — again the highest-value slice
- verifier:
  - sample: 22/49 (45%), stratified, weighted to load-bearing numbers; 30+ numeric claims traced
  - fabrications: 0; corrections: 5 precision fixes (unsourced consensus trio, unconfirmable ~3s, inferred origin, 2 citation-depth nits)
  - duplicates: 3 lineage seams flagged (AG2=AutoGen-0.2 fork; langgraph entry subsumption; agent-collection lineage) — noted in file, not merged
  - gaps: 5 named (CC Agent Teams first-party, Bedrock supervisor, Cursor 2.0 parallel, GitHub Agent HQ, Codex cloud) — reported to user, not researched to schema depth
  - verdict: ACCEPT WITH CORRECTIONS (applied)
- thin: none
- dedup-hotspots: framework lineage (forks/renames: AutoGen->AG2) is the seam class for vendor-partitioned sweeps — add a lineage-note rule instead of merging
- source-trust: official framework docs quote-stable; arXiv HTML full text verifies percentages exactly; HN item ids resolve stably; suspicious-looking precise numbers were ALL real this run
- steering: roster launched on direct sweep directive (logged precedent); no gate edits
- outcome: committed-at .claude/research-sweep/2026-09-12-conductor-landscape-findings.yaml; comparison delivered in-conversation (conductor 0.1.0 positioning)
- graduated: practitioner-scout 2nd useful run (1 more to stable); entity-scout first useful run in this repo; verifier row gains real-domain-not-fabricated (adk.dev) caution

## instruction-file-upkeep-2026-09-16  2026-09-16  alexmskills
- question: what else keeps an agent instruction file (CLAUDE.md/AGENTS.md/memory) current and bounded, and where does evolving-claude-md 1.6.1 sit?
- corpus: shipped CC/Codex ecosystem artifacts / vendor-native features + specs / practitioner lore + measured studies
- roster: container-scout(stable) + entity-scout(stable) + practitioner-scout(probationary, 3rd useful run -> STABLE) + verifier(skeptic) + synthesizer
- partition: by artifact locus (third-party shipped / vendor-native / practice+measurement), do-NOT-cover fences
- schema: findings{id,name,kind,origin,source_url,maintains,write_trigger,staleness_handling,size_control,enforcement,confidence}
- per-role: container 24 (target 14) · entity 30 (target 14) · practitioner 22 (target 12) · thin: none
- verifier:
  - sample: 37/74 (50%), plus all 9 named high-stakes numbers traced to source
  - fabrications: 0 (every repo, arXiv id and domain resolved, including risky-looking ones)
  - corrections: 10 — a WRONG-COLUMN read (NoLiMa 32K vs 64K), an unsourced quote, two wrong percentage sets, rule/type counts, an un-sourced parenthetical, an id collision, 5 too-coarse source_urls
  - gaps named: Amazon Q project rules, Kiro steering, Letta memory blocks (per-block char limits), Zep/Graphiti fact invalidation, Claude Code InstructionsLoaded hook, CodeRabbit learnings
  - verdict: ACCEPT WITH CORRECTIONS (all applied)
- dedup-hotspots: same-author lineage (roo-code-memory-bank -> ConPort) and wrapper/served-over-MCP pairs; annotate lineage rather than merge
- source-trust: vendor docs quote-stable and byte-exact; arXiv abstracts reliable, but a blog CITING a study is not — tianpan's "300-350 words" is attributed to a GitHub post that publishes no length figures, and the catalog held both halves without noticing. Rule: a number quoted second-hand must be traced to the primary before use.
- steering: launched on a direct sweep directive (no gate edits), same as the 09-12 run
- outcome: committed-at .claude/research-sweep/2026-09-16-instruction-file-upkeep-findings.yaml; comparison delivered in-conversation
- graduated: practitioner-scout -> STABLE (3 useful runs); verifier row gains the second-hand-citation rule
