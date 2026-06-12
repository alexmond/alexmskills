<!--
Graduate stable patterns for THIS repo into the block below, then paste it into
the repo's CLAUDE.md. Intake reads it to pre-fill the roster checkpoint.
Keep it short — it loads into context every session.
-->

## Dev crew

Recommended lineups for this repo (the crew still presents an editable roster;
this just sets the default):

- feature       -> architect(opus) -> dev(sonnet) -> qa(sonnet) -> deployer(haiku)
- bugfix        -> dev(sonnet) -> qa(sonnet)
- schema-change -> architect(opus) -> migration-specialist(opus) -> dev(sonnet) -> qa(sonnet) -> deployer(haiku)
- release       -> qa(sonnet) -> deployer(haiku)

Repo-specific tuning:
- <e.g. "qa must run `mvn -q verify` and the SpotBugs/PMD/ErrorProne gate before passing">
- <e.g. "deployer targets GitLab CE CI; stage the pipeline trigger, never push tags directly">
- <model re-tiers learned here, with reason>
