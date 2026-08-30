# The evidence contract

Every claim in a competitive review carries a **tier** and the citation form that tier requires. The
tier is not decoration — it tells a later reader how much weight the claim can bear, and it is the
difference between a document that survives a year and one that quietly becomes wrong.

## The three tiers

### MARKET — what they say about themselves

Pricing, licensing, positioning, roadmap, announced features, maintenance claims.

- **Requires:** a source URL **and the date you retrieved it**.
- **Phrase as:** "Priced at $X/user/month ([pricing](url), retrieved 2026-08-29)."
- **Never phrase as:** "Costs $X." — pricing changes, and an undated claim cannot be re-checked.

Vendor documentation is authoritative for *intent* and unreliable for *current state*. A docs page
saying a feature exists is a MARKET claim even when the feature is technical. Keep the distinction.

### REPO — what the project's metadata shows

Alive/dead, activity, release cadence, licence, stars, contributor count.

- **Requires:** host API metadata, captured verbatim rather than summarized from memory.
- **Phrase as:** "Archived 2026-01-21; last release 7.14.0, 2025-10-30."
- **Never phrase as:** "Seems abandoned." — that is an inference; give the reader the metadata.

### CODE — what the implementation actually does

"It computes X this way", "it does not handle Y", "the write path silently succeeds".

- **Requires:** `path/to/file.ext:LINE` at a **pinned commit** in a local checkout.
- **Phrase as:** "Hashes the path rather than the contents (`src/services/asset.ts:142`, at `a1b2c3d`)."
- **Never phrase as:** "Their dedup is broken." — a conclusion with no line behind it is hearsay, and
  it is exactly the kind of claim that gets repeated until someone builds a roadmap on it.

CODE claims are the only ones that let you say what a competitor *does* rather than what it *says*.
They are also the only ones that expire silently — the line moves and nobody notices. Always pin.

## The four rules

### 1. `(unverified)` is a first-class marker

Anything you could not confirm is marked inline **and** collected into a caveats register at the end
of the document. The header states plainly that these must not be quoted as fact.

The register is not an admission of weakness. It is the single most useful section for the next
person, because it tells them exactly where to spend their verification budget.

### 2. Unverified-negative is not false

Three different statements, three different labels:

| Statement | Label |
|---|---|
| "It does not have X" — upstream says so, or the source shows its absence | a finding |
| "We found no evidence of X, and no upstream denial" | **unverified-negative** |
| "It has X" — but we could not confirm | *(unverified)* |

Uniqueness claims about your own project are nearly always unverified-negative: "we are the only tool
that does X" usually means "we did not find a counterexample". Say that. It is still a useful
positioning claim, and it is honest about what would overturn it.

### 3. A documented capability is a MARKET claim

"The docs say it does X" and "it does X" are different claims. Tier the first as MARKET. Promote it
to CODE only by reading the source. Projects document intentions, deprecated behaviour, and features
that were removed without a docs update — this is one of the most common sources of a wrong review.

### 4. Staleness budget — 90 days

Pricing, licensing, and AI/LLM-feature claims expire 90 days after retrieval. Past that they are
flagged for re-verification, not reused. These are the fastest-moving facts in any category, and a
stale pricing claim is the one most likely to be quoted externally and embarrass someone.

Structural claims — architecture, delivery model, language — age much more slowly and do not need
the same budget.

## What a good caveats register looks like

Group by kind, name the specific claim, and separate genuine unknowns from unverified-negatives:

> **Caveats carried from research.** Marked *(unverified)* in-text and repeated here: [vendor]'s
> transport mechanism; whether [vendor] exposes [capability]; [vendor]'s scale numbers.
> **Unverified-negatives** (no positive evidence found, no explicit upstream denial): [capability]
> for [vendors]. Our claim to be the only [X] doing [Y] is **absence of evidence, not proof**.
> Pricing for several vendors is sales-quoted and could not be confirmed. **Re-verify any pricing or
> AI-feature claim before external use.**
