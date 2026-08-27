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
