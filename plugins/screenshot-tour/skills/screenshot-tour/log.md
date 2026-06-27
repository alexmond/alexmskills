<!-- SHIPPED SEED — read-only when installed as a plugin. The live, append-only log
     lives at <repo>/.claude/screenshot-tour/log.md; the skill copies this schema
     there on first run. Never write to this installed copy. -->
# screenshot-tour run log

Append-only. The learning loop reads this to graduate stable capture methods,
drop tools that consistently fall back to manual, and lift cross-run patterns
into the repo's `## Screenshot tour` CLAUDE.md block. One entry per tour run.
Newest at the bottom.

## Entry schema

```
## <run-id>  <yyyy-mm-dd>  <repo>
- product-type: <cli | web | library | tui | mixed>
- aspects-planned: <n>   aspects-captured: <m>   aspects-fallback: <k>   aspects-cut: <j>
- tools-used:
  - vhs: <n captures, GIF/PNG/MP4 mix>
  - playwright | selenium | selenide | cypress | shot-scraper | <other>: <n captures, viewport, browser>
  - freeze: <n captures>
  - manual: <n captures, what + why automation failed>
- gotchas: <e.g. ttyd missing in container; VHS wayland incompatibility; Selenium CDP only on Chrome; Playwright first-install bandwidth; secrets-in-screenshot near-miss>
- steering: <what the user edited in the plan — added X, cut Y, reframed Z; changed dimensions, theme, narrative order>
- outcome: <committed-at presentation/ | partial | abandoned | reused-from-prior-run>
- graduated: <what lifted to `## Screenshot tour` block in CLAUDE.md this run, if any — canonical aspect, standard dimensions, theme, default tool per surface>
```

---

<!-- entries below -->
