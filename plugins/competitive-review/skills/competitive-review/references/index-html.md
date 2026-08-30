# The `index.html` companion

A single self-contained page next to the markdown: sticky nav, the matrices, the per-competitor
cards. **No build step, no external assets, no CDN** — it must open from `file://` and survive being
emailed or copied to a machine with no network.

It is a *companion*, not a replacement. The markdown stays canonical and diffable; the HTML is for
reading the matrices without horizontal scrolling and for handing to someone who will not open a repo.

## Rules

- Everything inline — CSS in one `<style>`, no fonts, no scripts unless a behaviour genuinely needs
  one (nav scroll-spy does not).
- **The status vocabulary is the markdown's legend**, with one class per state, so the two documents
  cannot drift: `.first-class` ✅ · `.partial` ⚠️ · `.none` ❌ · `.na` —.
- Your own column is visually distinguished in every matrix, and pinned left.
- Wide tables scroll **inside their own container**; the page body never scrolls sideways.
- Carry the review date and the same provenance caveat as the markdown header. A page that escapes
  without its caveat is exactly how an unverified claim gets quoted as fact.

## Shell

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title><subject> — competitive review</title>
<style>
  :root {
    --bg:#0f1117; --surface:#171b24; --border:#2a3344; --text:#e8ecf4; --muted:#9aa8be;
    --accent:#6ea8fe; --yes:#3dd68c; --no:#f07178; --warn:#ebc88d; --mine:#b392f0;
  }
  @media (prefers-color-scheme: light) {
    :root {
      --bg:#fbfbfd; --surface:#fff; --border:#dfe3ea; --text:#1a1d23; --muted:#5b6472;
      --accent:#2563cf; --yes:#1a7f4b; --no:#c03a45; --warn:#8a6100; --mine:#6b3fbf;
    }
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text); line-height:1.55;
         font-family:system-ui,-apple-system,"Segoe UI",sans-serif; }
  a { color:var(--accent); }
  .layout { display:grid; grid-template-columns:240px 1fr; min-height:100vh; }
  nav { position:sticky; top:0; height:100vh; overflow-y:auto; padding:1.25rem 1rem;
        border-right:1px solid var(--border); background:var(--surface); }
  nav a { display:block; padding:.3rem 0; color:var(--muted); text-decoration:none; font-size:.9rem; }
  nav a:hover { color:var(--accent); }
  main { padding:2rem 2.5rem; max-width:1200px; }
  .caveat { border-left:3px solid var(--warn); background:var(--surface);
            padding:.85rem 1rem; margin:1.5rem 0; color:var(--muted); font-size:.92rem; }
  .matrix-wrap { overflow-x:auto; border:1px solid var(--border); border-radius:6px; margin:1.25rem 0; }
  table { border-collapse:collapse; width:100%; font-size:.88rem; }
  th, td { padding:.5rem .7rem; border-bottom:1px solid var(--border); text-align:left;
           white-space:nowrap; }
  thead th { position:sticky; top:0; background:var(--surface); }
  tbody th { position:sticky; left:0; background:var(--surface); font-weight:500; }
  .col-mine { background:color-mix(in srgb, var(--mine) 12%, transparent); }
  .first-class { color:var(--yes); } .partial { color:var(--warn); }
  .none { color:var(--no); } .na { color:var(--muted); }
  .card { border:1px solid var(--border); border-radius:6px; background:var(--surface);
          padding:1rem 1.25rem; margin:1rem 0; }
  .card h3 { margin:0 0 .5rem; }
  .verdict { font-size:.78rem; text-transform:uppercase; letter-spacing:.04em;
             color:var(--muted); }
  @media (max-width:820px) {
    .layout { grid-template-columns:1fr; }
    nav { position:static; height:auto; border-right:0; border-bottom:1px solid var(--border); }
  }
</style>
</head>
<body>
<div class="layout">
  <nav>
    <strong><subject></strong>
    <p class="verdict">Reviewed YYYY-MM-DD</p>
    <a href="#summary">Summary</a>
    <a href="#category">The category</a>
    <a href="#matrix">Feature matrix</a>
    <a href="#competitors">Competitors</a>
    <a href="#gaps">Gaps &amp; differentiation</a>
    <a href="#adopt">What to adopt</a>
    <a href="#caveats">Caveats</a>
  </nav>
  <main>
    <h1><subject> — competitive review</h1>
    <div class="caveat">
      Based on public product information verified during research. Claims marked
      <em>(unverified)</em> could not be confirmed and must not be quoted as fact.
      Internal positioning document, not marketing copy.
    </div>
    <!-- sections -->
  </main>
</div>
</body>
</html>
```

## Generating it

Write it from the finished markdown, not alongside it — the markdown is the source of truth, and
generating second is what keeps the two consistent. In `render` mode this is the only step that runs.
