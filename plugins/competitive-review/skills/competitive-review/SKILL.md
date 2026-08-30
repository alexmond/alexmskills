---
name: competitive-review
description: >-
  Competitive analysis with an evidence contract: every claim tiered and cited, hypotheses that
  can come back falsified, liveness checked rather than assumed. Use for competitor analysis,
  competitive review, positioning, "how do we compare", "who else does this", "are we still
  ahead", or refreshing a stale review.

argument-hint: "[review | refresh | teardown <competitor> | render]"
---

# Competitive review

> **Try it:** `/competitive-review:competitive-review` in a project repo — or say "how does this compare to the competition", "run a competitor analysis", "is our positioning still true".

Finding the competitors is the cheap half. Any agent with a search tool produces a plausible list in
one pass, and that list rots within a quarter — half the entries are dead projects still showing
commits, a third of the claims came from a README that no longer matches the source, and nothing
records which claims were never actually confirmed.

The expensive half is **evidence discipline**, and it is what this skill exists for:

- **Hypotheses before evidence.** Falsifiable claims are written down *first*, so research can come
  back and falsify them. A review that only confirms what you already believed did no work.
- **Every claim carries a tier and a citation** — market, repo, or code. Unverifiable claims are
  marked, collected, and explicitly barred from being quoted as fact.
- **Liveness is investigated, not assumed** from a last-commit date.
- **Refresh reports what *changed*** — including which of your own claimed gaps you have since closed.

The output is an internal positioning document, not marketing copy. Write it so it can be trusted a
year later by someone who was not in the room.

## Scope check

This is the full pipeline: a fan-out, a verification pass, and a structured document. That is too
much machinery for a small question.

Hand the task to a single agent instead when:

- The user wants to know about **one** named competitor ("what does X do for Y") — that is a lookup.
- The question is a **feature check**, not a positioning question.
- The repo already has a current review and the ask is a single clarification against it.

Use the full pipeline when the ask is positioning, category-shaped, or plural: "who else does this",
"where do we actually win", "what should we build next", "is our thesis still true".

## Modes

Detect the mode from the ask and from whether `docs/competitive-review/competitor-analysis.md` exists.
**Say which mode you picked before starting** — they differ enough that a wrong pick wastes a run.

| Mode | When | What it does |
|---|---|---|
| `review` | no existing doc, or an explicit full review | The whole pipeline, cold |
| `refresh` | an existing doc is found | Diffs the world against the doc; reports what changed and what that invalidated |
| `teardown <competitor>` | "how does X actually do Y" | Deep code mode on one rival; appends an evidenced section |
| `render` | "rebuild the review page" | Regenerates `index.html` + screenshots from the existing markdown |

## Files this skill owns

- `<repo>/docs/competitive-review/competitor-analysis.md` — the canonical document.
- `<repo>/docs/competitive-review/index.html` — the self-contained companion page.
- `<repo>/.claude/competitive-review/log.md` — per-run evidence: hypotheses and their verdicts, thin
  slices, what the verifier caught. Seeded on first run from this skill's shipped `log.md`, which is a
  **read-only seed** — never write to the installed copy.
- `<repo>/.claude/competitive-review/sources.md` — the **source-trust ledger**: which registries proved
  authoritative for this category, which fabricate, which need a second source. This is the wisdom that
  compounds across runs; a fresh review in a known category should start already knowing where to look.
- Competitor checkouts, deep mode only — see "Deep teardown mode".

## The evidence contract

Every claim in the document sits in one of three tiers, and each tier has a citation form it must
carry. A claim that cannot meet its tier's bar is either downgraded or marked unverified — never
silently promoted.

| Tier | Claim type | Required evidence |
|---|---|---|
| **MARKET** | pricing, licensing, positioning, roadmap | source URL **plus retrieval date** |
| **REPO** | alive/dead, activity, stars, licence, releases | host API metadata, captured verbatim |
| **CODE** | "it implements X this way" | `file:line` at a pinned commit in a local checkout |

Four rules ride on top. They are not optional polish — each one exists because its absence has
produced a confidently wrong review:

1. **`(unverified)` is a first-class marker.** Mark inline, and collect every instance into a caveats
   register at the end of the document. The header states these must not be quoted as fact.
2. **Unverified-negative is not false.** "No positive evidence found, and no upstream denial" is a
   distinct label from "does not have it". Uniqueness claims about your own project are almost always
   this: absence of evidence, not proof.
3. **A documented capability is a MARKET claim, not a CODE claim.** "The docs say it does X" and "it
   does X" are different claims with different tiers. Keep them apart.
4. **Staleness budget.** Pricing, licensing, and AI/LLM-feature claims expire **90 days** after their
   retrieval date. Anything past its budget is flagged for re-verification, not quietly reused.

Full contract, with the phrasing to use for each tier: [references/evidence-contract.md](references/evidence-contract.md).

## Phase 0 — Frame, and commit to hypotheses

**Read the subject first.** Its `README.md` and `CLAUDE.md` describe what it is and what it bets on.
Write the "subject" paragraph from them — architecture, delivery model, licensing, the distinctive
bets — because every later comparison is relative to it.

Then write **2–4 falsifiable hypotheses** and put them in the document before any research runs.

A usable hypothesis names a thing that could be found to be false:

- Good: *"No self-hosted tool in this category treats X and Y as separate concerns."*
- Good: *"Our stack choice is a differentiator rather than a contributor liability."*
- Useless: *"We are well positioned."* — nothing could falsify it.

**Show the hypotheses to the user and get them approved before fanning out.** They are the spine of
the review; a bad set produces a well-researched answer to the wrong question. This is the one gate
in the pipeline.

Expect at least one to come back false. That is the review working, and the falsification is usually
the single most valuable paragraph in the document — record what survives and what replaces the claim.

## Phase 1 — Discover

**Commit to the schema before launching anything.** Agents that return subtly different shapes cannot
be merged. Lock the entry fields (`id`, `name`, `url`, `slice`, `delivery_model`, `licence`,
`evidence` …), the tier rules, and the forbidden behaviours — no fabrication, omit unknown fields
rather than guess — and paste that block **verbatim** into every agent prompt.

**Partition into disjoint slices.** Competitive spaces have their own natural axes, which are not the
generic ones: by **market slice**, by **delivery model**, by **adjacency ring**, by **era of entry**.
Pick the axis that carves *this* category cleanly; overlapping slices produce duplicate work and merge
conflicts at the seams. See [references/partition-axes.md](references/partition-axes.md).

Aim for 4–6 slices. Each prompt carries: one line of context, the schema verbatim, the slice it owns
and nobody else touches, source guidance, the verification rules, a numeric floor so the agent does
not stop at the famous three, "return YAML only in a fenced block", and **"answer directly — do not
spawn sub-agents and do not wait on anything"**. Without that last clause an agent may delegate its
slice and then return a progress report instead of data, burning its whole budget on coordination.

Launch them **in a single message** so they run concurrently, with `run_in_background: true`.

**Extract with `jq`, never by reading the transcripts** — they are full conversations and will blow
out context:

```bash
TASKS=~/.claude/projects/<encoded-cwd>/<session-id>/subagents
{
  echo "competitors:"
  for id in <agent-ids>; do
    F="$TASKS/agent-$id.jsonl"; [ -f "$F" ] || continue
    echo "  # === agent $id ==="
    jq -rs '[.[] | select(.type=="assistant")] | last | .message.content[]? | select(.type=="text") | .text' "$F" \
      | awk '/^```yaml/{f=1;next} /^```$/{f=0;next} f'
  done
} > /tmp/competitors.yaml
grep -c '^  - id:' /tmp/competitors.yaml
```

A thin slice is a **diagnosis, not a verdict**. Classify before re-running:

- **slice-thin** — the slice genuinely holds few players. Lower the floor and note its true depth.
- **agent-thin** — the slice is plentiful but the agent under-delivered: it stopped at the famous
  few, lost its web tools, or **went off-contract** (delegated, then reported status instead of data).
- **wrong angle** — the slice does not carve this category. Re-cut it rather than re-running it.

An off-contract agent is usually **recoverable**: it still holds its research, so resume it with a
corrected brief — answer directly, no delegation, output the schema — before paying for a cold
re-run. Log which diagnosis it was and what fixed it.

## Phase 2 — Verify

Two passes, and neither is skippable. Fan-out without verification produces confident garbage at scale.

**Liveness forensics — mechanical, run over every competitor.** A last-commit date is not evidence of
life. Check the archived flag, find the last *substantive* commit with bot and no-op batches filtered
out, and diff documented capabilities against what the source actually still contains. Dead and dying
competitors are among the most valuable findings in a review — each one is a lesson about the
category. Procedure and the known traps: [references/liveness-forensics.md](references/liveness-forensics.md).

**Adversarial verification — by a fresh agent that did not gather the data**, so it has no stake in
defending it. Its mandate: spot-check a 10–20% sample against primary sources; hunt fabricated URLs,
dates and version numbers; check the seams between slices where duplicates cluster; and name what is
**missing** — an obvious competitor nobody returned is a coverage failure exactly as much as a wrong
entry is.

Fold its findings in as concrete fixes, and record the fabrication-prone sources in `sources.md`.

## Phase 3 — Analyze

The document's analytical core, in this order:

1. **The category map** — a `slice → owner(s) → our stance` table. This is what turns a list of
   rivals into a shape, and it is where "the category is fragmented" either becomes visible or fails
   to. If every slice has the same owner, the category is not fragmented and the thesis must change.
2. **Feature matrices**, grouped by segment rather than one unreadable wide table. Legend:
   `✅ first-class · ⚠️ partial / add-on / awkward · ❌ not offered · — N/A`.
3. **Per-competitor notes**, each in the same fixed shape: what it is, **we win**, **they win**, and a
   **watch item** where it is moving toward you.

The **they win** line is mandatory and must be substantive. A review in which no competitor beats you
at anything is not a review; it is an advertisement, and it will get someone's roadmap wrong.

## Phase 4 — Decide

The "so what". Without it the document is trivia:

- **Where we must not lose** — the table-stakes battlegrounds, named explicitly.
- **Best features to adopt**, prioritized, each tied to the competitor that proves the need.
- **Candidate offensive moves** — the ones that extend a lead rather than close a gap. Keep these
  separate from the defensive-parity list; conflating them is how a roadmap becomes all catch-up.
- **The hypotheses, tested** — each one confirmed, falsified, or refined, with what replaces it.
- **One-line thesis** and **bottom line**.

Write the adopt-list so each item could become a ticket. Do not file tickets — that is the user's call.

## Refresh mode

The point is the **delta**, not a fresh document. Read the existing review, take its review date, and
report against it:

| Signal | What to report |
|---|---|
| `DIED` | competitors now archived or provably dormant since the last review |
| `NEW` | entrants that did not exist or were missed |
| `FALSIFIED` | hypotheses or claims the world has since disproved |
| `STALE` | **the subject's own rows** — capabilities marked planned that have since shipped |
| `DRIFT` | claims past their staleness budget, needing re-verification |

`STALE` is the one that gets forgotten. Your own project moves fastest of anything in the document,
so its column rots first — read the repo's own change log or `CLAUDE.md` to catch it.

Update the document in place, keep the original review date alongside the refresh date, and mark
revised sections with the date they were revised so a reader can tell new analysis from old.

## Deep teardown mode

Opt-in, per competitor, for open-source rivals only. This is what promotes a claim from "their docs
say" to "their code does".

1. **Prefer a checkout that already exists** on the machine before cloning anything — but **verify it
   is upstream before trusting a line of it.** An existing local clone is usually a fork you have
   patched, and your patches sit exactly where you believe the competitor is weakest. Check
   `git status --porcelain` for uncommitted work and `git log <pin>..HEAD` for local commits, then
   read every cited file with `git show <pin>:<path>` rather than from the working tree.
2. Otherwise clone shallow into a durable workspace — `${COMPETITIVE_REVIEW_WORKSPACE:-$HOME/.cache/competitive-review}/<owner>-<repo>` — so later runs update rather than re-clone.
3. **Pin the commit** and record it. Every CODE claim cites `path/to/file.ext:LINE` and is only valid
   at that commit. If you are also comparing against a *running* instance, record its released
   version too — a checked-out `main` is routinely ahead of anything deployed, and a claim read from
   it can describe a version nobody runs. Where source and deployment disagree, say so.
4. Read in order: entry points, the module that owns the behaviour in question, its tests, and the
   release notes around it. Tests are the highest-signal source for what a project believes it does.
5. Never let a CODE claim outlive its pin. On refresh, re-resolve the line or re-verify the claim.

Reserve this for competitors where an implementation detail is load-bearing for your positioning. It
is expensive, and most rivals do not warrant it.

## Artifacts

- **`competitor-analysis.md`** — the canonical document. Section-by-section template, with the header
  block and caveats register: [references/document-template.md](references/document-template.md).
- **`index.html`** — self-contained companion: sticky nav, the matrices, no build step and no external
  assets, so it opens from disk and survives being emailed. Shell:
  [references/index-html.md](references/index-html.md).
- **UI benchmark screenshots** under `docs/images/`, when the category is one where the interface *is*
  the product. Use the repo's existing browser driver; if a screenshot skill is installed, defer to it
  rather than hand-rolling capture.

## Learning loop

After each run, write back — the next review in this category should not start from zero:

- **`log.md`** — one entry per run: the hypotheses and their verdicts, which slices ran thin and why,
  what the verifier caught, which sources fabricated.
- **`sources.md`** — the source-trust ledger. Authoritative registries for this category, sources that
  fabricated, and the traps that liveness forensics caught here.
- **Graduate** a pattern into the repo's `CLAUDE.md` under a `## Competitive review` block once it has
  held across three runs — the standing competitor set, the category's authoritative sources, the axis
  that carves it cleanly. Then prune the graduated entries from `log.md` so it stays evidence rather
  than history.

## Anti-patterns

- **Don't research first and write hypotheses after.** They become a summary of what you found, they
  can never be falsified, and the most valuable section of the document is lost.
- **Don't infer death from a last-commit date**, or life from a recent one. Both mislead; investigate.
- **Don't let a documented capability become a factual one.** Tier it as MARKET and move on.
- **Don't write a review where no competitor beats you.** If that is the finding, the research is
  incomplete or the comparison set is too flattering.
- **Don't drop the unverified markers when tidying.** They are the document's integrity, and they are
  exactly what a later reader needs most.
- **Don't skip Phase 2** because the fan-out returned a lot. Volume is not accuracy.
- **Don't re-run a full review when the ask is a delta.** Refresh mode exists so the changes stay
  legible instead of being buried in a rewrite.
