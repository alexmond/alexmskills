# Demo & promotion practices for alexmskills — survey synthesis

**Date:** 2026-08-27 · **Method:** research-sweep, 3 coverage scouts (52 cited
findings) + adversarial verification (12/12 spot-checks held, 0 fabrications).
Raw findings: `.claude/research-sweep/2026-08-27-demo-promo-findings.yaml`.

## The headline

The ecosystem's reference repos leave show-don't-tell on the table:
**anthropics/skills and obra/superpowers ship zero recordings** — text-only
READMEs. Meanwhile the house style of the surrounding CLI world (and of
anthropics/claude-code itself) is a committed root `demo.gif`. A skills
marketplace that demos its skills visually is *differentiating*, not catching
up. On the promotion side, the audience actively discounts launch-post noise —
official-directory vetting and awesome-list curation are the trust signals
that move installs.

## Adopt — tier 1: format (cheap, this repo, this week)

1. **Root `demo.gif` in the README** (atuin, anthropics/claude-code pattern).
   Produce with VHS; keep under ~5 MB (GitHub hard cap 10 MB); GIF, not MP4
   (MP4 embeds break off github.com — IDE previews, mirrors).
2. **Per-plugin `demo/` dir with a committed `demo.tape` + rendered GIF**
   (precedent: davila7's loki-mode skill; convention: charmbracelet "view
   source" caption linking the tape). One short GIF per plugin beats one long
   tour (gum pattern). Start with 2–3 flagship plugins (progress-channel's
   live page, prompt-coach's nudge, dev-crew's relay), not all 17.
   Regenerate in CI later via charmbracelet/vhs-action so demos can't rot.
3. **A "try this prompt" line per catalog row** (pm-skills pattern) — skills
   trigger on phrasing, so showing the phrase IS the demo. Several SKILL.mds
   already carry `> Try it:` lines; surface them in the README catalog.
4. **Counts headline** ("17 plugins · N skills · N agents") + a one-phrase
   "why you need it" angle in catalog descriptions (karanb192 pattern — ours
   say *what*, rarely *why*).
5. **Generate the README catalog table from marketplace.json** (hesreallyhim
   generates from CSV; tons-of-skills regenerates from its manifest in CI).
   This kills the README-row drift that has already bitten twice (progress-
   channel 0.2.0, dev-crew 1.3.0 — `make bump` doesn't touch the README).
6. **GitHub topics**: add `claude-skills` (7.5k repos), `claude-code-plugins`
   (505 repos — the marketplace shelf), `claude-code`, `claude-ai`.
   Aggregators (SkillsMP ~2M skills) index by crawl — topics + valid SKILL.md
   frontmatter are the listing mechanism; there is nothing to submit.

## Adopt — tier 2: listings (ordered by bar, after tier 1)

1. **anthropics/claude-plugins-official** via the submission form at
   clau.de/plugin-directory-submission — submit the 1–2 strongest plugins,
   not the catalog. Highest trust signal in the ecosystem (community
   explicitly waits for Anthropic vetting; a Superpowers-inclusion post drew
   238 upvotes on that fact alone).
2. **skills.sh** — list and add the badge (anthropics/skills itself carries
   it); the only channel with public install metrics.
3. **Awesome lists, in bar order**: BehiSecc/awesome-claude-skills (plain PR,
   low bar) → VoltAgent/awesome-agent-skills (cross-tool audience, org-level
   listing) → hesreallyhim/awesome-claude-code (issue form ONLY, qualifies
   via 14-days+active; badge on acceptance) → travisvn/awesome-claude-skills
   (needs 10+ repo stars first; one skill per PR, exact one-line format).
4. **claudemarketplaces.com** ranks by stars + registry metadata — no
   outreach lever; it follows from everything above.

## Adopt — tier 3: announcements (only with an artifact in hand)

- **Reddit launch = problem-story format** (claude-mem template, 233⇧/130
  comments → 92k stars): pain → "what I built" → mechanism bullets, personal
  voice, zero marketing tone. Best candidates here: prompt-coach or
  progress-channel — both have a visceral pain story.
- **Later, a metrics retro** (graphify pattern, ~1.8k⇧): numbers in the
  title, "what I didn't expect", end with two questions to the community.
- **HN only with a spectacular concrete demo** — 30+ "Show HN: Claude
  skill…" posts landed 2–7 points; the one breakout (337 pts) had a visceral
  artifact. A bare marketplace Show HN sinks; a progress-channel live-page
  GIF might clear the bar.
- **Unexplored channels the sweep verifier flagged** (no findings, worth a
  follow-up pass): X build-in-public threads, YouTube AI-coding creators,
  the Claude Developers Discord, newsletters (Simon Willison / TLDR),
  Product Hunt.

## Explicitly not adopting

- Multi-harness install matrices / harness badges (superpowers, wshobson) —
  not until skills target more than Claude Code.
- Catalog offloading to docs/*.md (wshobson) and job-bundle discovery sites
  (tons-of-skills) — oversized at 17 plugins.
- Freshness badges per entry — single-owner marketplace; version column
  already carries the signal.
- vhs.charm.sh hosting for demo GIFs — third-party-controlled URLs; commit
  the GIFs (or an assets repo à la fzf if repo weight becomes a problem).

## Evidence quality note

12-finding adversarial sample: all verified or corroborated; two Reddit
scores and one blog quote are approximate (Reddit blocks re-fetching; the
quoted page supports the gist but not the sentence). Nothing load-bearing
rests on those three.
