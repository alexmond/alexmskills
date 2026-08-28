# research-sweep coverage-roles registry

One row per coverage role. Same mechanism as `crew.md` / `panel.md` — status
lifecycle probationary → stable (3+ useful runs), demote on 2 thin runs, retire
on 3 (or 3 user-cuts at the roster gate). Verifier (shared `skeptic`) and
synthesizer are persistent seats, listed here for tier/learnings tracking.

## Coverage roles

### container-scout
- charter: partition by corpus — one collection/marketplace/registry per agent
- when-to-cover: the space splits cleanly across repos, registries, or indexes
- model: sonnet
- status: stable (archetype seed)
- learnings:

### source-scout
- charter: partition by where evidence lives — docs, code hosts, papers, news
- when-to-cover: the same facts surface in different source types with different trust
- model: sonnet
- status: stable (archetype seed)
- learnings:

### entity-scout
- charter: partition by actors — authors, orgs, vendors, labs
- when-to-cover: the space is driven by identifiable actors with bodies of work
- model: sonnet
- status: stable (archetype seed)
- learnings:

### timeline-scout
- charter: partition by period — eras, generations, release windows
- when-to-cover: strong temporal spread; practices/entries differ by era
- model: sonnet
- status: stable (archetype seed)
- learnings:

### promotion-scout
- charter: how a project is announced, listed, and discovered — awesome lists, directories, social/blog announcements, badges, install UX
- when-to-cover: the question is about visibility/adoption practice, not the artifact itself
- model: sonnet
- status: probationary (minted 2026-08-27, demo/promotion survey)
- learnings:
  - 2026-08-27 — 1 useful run (17/14 findings, 0 thin). Reddit blocks direct fetch — use a headless browser or corroborate scores via HN/press mirrors; heaviest slice by tool calls (44).

### practitioner-scout
- charter: practitioner-written practice and failure lore — blogs, HN/Reddit threads, talks, measured studies — about a tool/format's real-world use
- when-to-cover: the question needs what practitioners say works/fails, distinct from official prescription and from shipped artifacts
- model: sonnet
- status: probationary (minted 2026-08-28, CLAUDE.md practices survey)
- learnings:
  - 2026-08-28 — 1 useful run (26/15 findings, 0 thin). Best slice for MEASURED sources (arXiv, corpus analyses); mark measured claims explicitly in evidence — they outrank the opinion pool at synthesis time.

### demo-tooling-scout
- charter: how demos are produced and embedded — terminal recorders (VHS/asciinema), GIFs, screenshots, videos, hosted playgrounds
- when-to-cover: the question is about show-don't-tell mechanics for CLI/agent tooling
- model: sonnet
- status: probationary (minted 2026-08-27, demo/promotion survey)
- learnings:
  - 2026-08-27 — 1 useful run (18/14 findings, 0 thin). Primary-docs constraints (GitHub media limits) verify cleanly; GitHub code search by file extension (.tape) is a strong precedent-finder.

## Persistent seats

### verifier (shared skeptic)
- charter: adversarial spot-check of the merged findings against primary sources; hunts fabrication, seam duplicates, papered-over thin slices, gaps
- model: sonnet
- status: stable
- learnings:
  - 2026-08-27 — quote-via-search misattribution is a real FP class: a page can exist and support the gist while lacking the quoted sentence — fetch the cited page before trusting a quote. Reddit scores are un-recheckable by fetch; downgrade them to approximate rather than refuting.
  - 2026-08-28 — repo-file claims (sizes, line counts, section names) verify byte-exact via raw.githubusercontent.com — sample them preferentially; they're the cheapest high-confidence checks. Genuine cross-source contradictions (official vs practitioner vs measured) are findings, not defects — verify each side reports its OWN source faithfully.

### synthesizer
- charter: dedup across angles, assemble the cited result, own the seams
- model: (main session)
- status: stable
- learnings:
