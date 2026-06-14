---
name: tune-repo
description: >-
  Audit and tighten the current repository so Claude Code works faster and more accurately in
  it — verify the existing CLAUDE.md still matches reality, tighten the build/test/lint
  verification loop, add only the missing static guardrails, and reduce permission friction.
  Use when the user wants to "tune", "audit", "harden", or "onboard" a repo for Claude/AI
  agents, fix a stale or thin CLAUDE.md, or make agent runs more reliable. Works in any repo;
  pass "audit" to report without changing anything.
---

# tune-repo

Make a repository a place where Claude Code performs at its best: an accurate CLAUDE.md, a
single fast deterministic verification command, enforced static guardrails, and low permission
friction. The biggest accuracy killer is a **stale** CLAUDE.md — a wrong instruction is worse
than a missing one — so this skill verifies claims against reality before adding anything.

Run the three phases below. If the user's request contains `audit`, do Phases 1–2 only and
apply nothing. Make minimal, idiomatic changes; **never weaken an existing guardrail**; never
invent a convention the repo doesn't already follow.

## Calibrate to the project (don't impose a generic template)

Discover the repo's own conventions and match them. If sibling repositories exist in the parent
directory, read the closest **well-tuned** one (the one with the most complete CLAUDE.md +
enforced guardrails) and use it as the template, so a fleet of related repos converges on one
house style instead of drifting.

Map common stacks to their guardrails and one-shot verify command, but confirm what the repo
actually uses before proposing anything:

- **Java / Maven or Gradle** — formatter (e.g. spring-javaformat / Spotless), Checkstyle, PMD,
  and a JaCoCo coverage gate; verify via `mvn verify` (often wrapped in a `scripts/dev-verify.sh`
  that formats then runs the full build, plus a `scripts/dev-test.sh <selector>` for one test).
  The `maven-quality` plugin provides these skills for Java/Maven repos.
- **JS / TS** — Prettier/Biome + ESLint + `tsc --noEmit` + the test runner; verify via the
  package script that chains them (e.g. `npm run check`).
- **Python** — ruff/black + mypy + pytest; verify via the project's task runner.
- **Go / Rust** — `gofmt`/`vet`/`golangci-lint` + `go test`; `fmt`/`clippy` + `cargo test`.

For a non-code repo (docs, plugin/marketplace, infra), infer the verify command and guardrails
from its own tooling or the closest sibling.

**On sibling conflicts, prefer the in-repo working tool.** If this repo already uses
spring-javaformat and the sibling uses Spotless, the in-repo tool stays — swapping a working
guardrail for a different one is churn. Surface the divergence in Phase 2 as a finding for the
user to decide, never silently align.

## Phase 1 — Discover (read-only)

Determine: language and build tool; the exact build, test, lint, and format commands; what CI
enforces; whether tests are fast and hermetic (no network/clock/randomness); the module/package
layout and the largest source files; and read the existing `CLAUDE.md` and `.claude/` settings.
Then open the sibling template (if any) to capture house conventions.

## Phase 2 — Audit (report findings, each citing `file:line`)

1. **CLAUDE.md accuracy** — verify EVERY command, path, flag, and claim it states still exists
   and works today. Flag anything stale or wrong. This is the top accuracy lever.
2. **CLAUDE.md completeness** — does it concisely give: the one-command build+test+lint; a module
   map; code conventions; how to verify a change; and the top gotchas that otherwise cost
   trial-and-error? Target *coverage*, not line count: a tiny repo needs less than a 50k-LOC
   monorepo. ~80–120 lines is a typical ceiling, not a quota — stop when each section earns its
   keep.
3. **Verification loop** — is there a single, fast, deterministic command that builds + tests +
   lints, and can Claude run it without prompts? If not, propose one (matching the sibling/house
   pattern, e.g. a `scripts/dev-verify.sh`).
4. **Static guardrails** — formatter, linter, static analysis, and coverage gate present and
   enforced both locally AND in CI? They are Claude's correctness oracle: precise, fixable
   feedback that catches agent mistakes automatically. Prefer enforcing existing tools over
   adding new ones; only adopt missing house guardrails if a sibling already standardises them.
5. **Permission friction** — are common safe, read-only commands and the repo's own scripts
   allowlisted in `.claude/settings.json` so Claude isn't blocked mid-task? Never allowlist
   destructive commands. If `fewer-permission-prompts` is available, delegate the transcript
   mining to it rather than re-deriving the allowlist here; this phase just owns the *audit*
   of the result.
6. **Structure** — oversized/god files, hidden wiring that isn't greppable, non-hermetic tests.

**Example audit output** (one finding per line, each with file:line + a one-line "why it costs
accuracy or speed"):

> 1. `CLAUDE.md:42` — claims `make test` runs JUnit; repo migrated to Gradle in 2026-05 (`build.gradle.kts:1`).
>    *Stale command → agents run the wrong tool and waste a cycle.*
> 2. `CLAUDE.md` missing the one-shot verify command. *Agents stitch their own, inconsistently.*
> 3. `pom.xml` enforces Checkstyle locally but `.github/workflows/ci.yml:38` skips it on PR. *Drift sneaks in.*
> 4. `.claude/settings.json` lacks `mvn -pl :*-api compile` allowlist; sibling repo `unitrack` allowlists it.
>    *Three permission prompts per typical run.*

## Phase 3 — Propose, then (on approval) apply

Present a prioritized, minimal change set, each line with a one-line "why this improves accuracy
or speed":

- correct CLAUDE.md to match reality and the house shape (keep it concise);
- tighten or add the one-shot verification loop;
- add only the missing house guardrails (formatter / linter / static analysis / coverage),
  matching the sibling configs;
- reduce permission friction in `.claude/settings.json`.

Do not relax existing checks. After approval, apply the changes and **run the repo's own
verification command to prove nothing broke**. End with a short summary of what changed and any
follow-ups worth a ticket.

**Example change set** (each line tied to a Phase 2 finding):

> 1. `CLAUDE.md:42` — replace `make test` block with the current `./gradlew check` flow.
>    *Fixes finding 1; restores accuracy on the top-of-doc command.*
> 2. Add `scripts/dev-verify.sh` wrapping `./gradlew clean check` and document it in `CLAUDE.md`.
>    *Fixes finding 2; gives agents one deterministic command.*
> 3. `.github/workflows/ci.yml:38` — drop the `-Dcheckstyle.skip=true` override.
>    *Fixes finding 3; lets CI catch what local already does.*
> 4. `.claude/settings.json` — allowlist `mvn -pl :*-api compile` per sibling's pattern.
>    *Fixes finding 4; cuts three prompts per run.*
>
> ~~Reformat all sources with Spotless~~ — *deferred: this repo uses spring-javaformat (working);
> flagged as divergence from sibling for your call.*

## Companions

- `maven-quality` — installs the actual format/Checkstyle/PMD/JaCoCo/precommit skills this audit
  recommends for Java/Maven repos.
- `evolving-claude-md` — keeps CLAUDE.md healthy over time (this skill is the one-shot tune-up;
  that one is the ongoing maintenance loop).
