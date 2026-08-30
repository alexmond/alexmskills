# Liveness forensics

**A last-commit date is not evidence of life, and a quiet repo is not evidence of death.** Both
mislead, in opposite directions, and both mislead often enough that guessing produces a wrong review.
Dead and dying competitors are among the most valuable findings a review can carry — each one is a
lesson about what the category punishes — so they are worth getting right.

Run this over **every** competitor, mechanically, in Phase 2.

## The metadata pass

```bash
gh api repos/OWNER/REPO --jq '{archived, disabled, pushed_at, created_at,
  stars: .stargazers_count, licence: .license.spdx_id, open_issues: .open_issues_count}'

gh api repos/OWNER/REPO/releases --jq '.[0:3] | map({tag: .tag_name, date: .published_at, draft, prerelease})'

gh api repos/OWNER/REPO/commits --jq '.[0:30] | map({date: .commit.author.date,
  author: (.author.login // .commit.author.name), msg: (.commit.message | split("\n")[0])})'
```

Capture the output verbatim into the entry. A summarized-from-memory REPO claim is not a REPO claim.

## The five traps

### 1. The no-op commit batch

An organization sweeps every repository it owns — a licence header, a CI config, a bot bump, a
`.github` template. The repo shows commits this month; real development stopped years ago.

**Detect it:** look at the last 30 commit *messages and authors*, not the dates. If they are all bot
authors, or the same message appears across many repos in the org on the same day, the project is
dormant. Report the last **substantive** commit and say how you determined it.

> "2026 commits are an org-wide no-op batch across ~50 repos; real activity stopped 2023-07-07."

### 2. README-vs-source drift

The README documents an integration, plugin system, or backend that no longer exists in the source.
Readmes are marketing surfaces and are rarely pruned.

**Detect it:** for any capability that matters to your positioning, grep the source for it before
believing the README. This is the cheapest promotion from MARKET to CODE tier you will ever get, and
it regularly overturns a comparison row.

### 3. Archived-but-recommended, and the live fork

An archived project often points at a successor, and the successor may be the real competitor. The
reverse also happens: a dead upstream with a fork carrying all the actual activity.

**Detect it:** read the archive notice and the README banner. Check the fork network for a fork with
more recent activity than the original. A dead original plus a live fork is *two* entries — with
different verdicts — not one.

### 4. Release cadence vs commit cadence

A project can commit daily and not have shipped in two years, or ship steadily from a quiet repo
because development happens elsewhere. Neither number alone tells you whether users are being served.

**Detect it:** compare the last release date to the last substantive commit. A wide gap in either
direction is itself a finding worth a sentence.

### 5. Stars are a lagging indicator

Star counts accumulate and never decay, so a dead project keeps the stars it earned. Never use stars
as an activity signal. They are useful for one thing only: rough audience size at the moment of
measurement, which is why the retrieval date matters.

## Classifying the result

Write one of these into every competitor's entry, with the evidence that produced it:

| Verdict | Criteria |
|---|---|
| **Active** | substantive commits and a release inside the last ~6 months |
| **Maintained** | substantive commits, no recent release — bug fixes, no direction |
| **Dormant** | no substantive commits in ~12 months, not archived |
| **Dead** | archived, or dormant with an explicit end-of-life notice |
| **Superseded** | dead, with the maintainers pointing at a named successor |

A `Dead` or `Superseded` verdict earns a line about **why** it died. That lesson is the reason the
entry stays in the document rather than being deleted.
