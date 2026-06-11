<!--
Written by dc-scout on init, read by the conductor every run. Lives at
<repo>/.claude/dev-crew/PROFILE.md. Re-generate with "re-profile" after a stack
change. Keep it tight.
-->

# Project profile — <repo>

- profiled: <yyyy-mm-dd>  by dc-scout
- languages: <e.g. Java 17 (primary), some shell>
- build/package: <e.g. Maven — `mvn -q verify`>
- frameworks/libs: <e.g. Go-templates + Sprig as the templating layer>
- test stack: <framework + exact run command>
- quality gate: <e.g. SpotBugs + PMD + ErrorProne — runs as part of `mvn verify`>
- CI: <e.g. GitLab CE (.gitlab-ci.yml) + GitHub Actions>
- deploy/runtime: <e.g. Docker images; k3s homelab; local registry>
- domain: <one line>
- conventions (from CLAUDE.md): <commands/style/do-don't the crew must honor>

## Recommendations (drives the roster checkpoint)

- per-category lineups:
  - feature       -> architect(opus) -> dev(<tier>) -> qa(sonnet) -> deployer(haiku)
  - bugfix        -> dev(<tier>) -> qa(sonnet)
  - <category>    -> <lineup>
- dev tier for this repo: <haiku|sonnet|opus> — because <mainstream/idiomatic vs exotic/correctness-critical>
- pre-arm candidate roles: <e.g. migration-specialist (schema files present), reviewer (large, convention-heavy)>
- qa quality-gate command: <exact command qa must run before passing>
- deployer CI target: <e.g. stage GitLab CE pipeline trigger; never push tags directly>
