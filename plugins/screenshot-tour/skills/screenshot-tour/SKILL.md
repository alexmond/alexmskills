---
name: screenshot-tour
description: Generate a presentation-worthy screenshot deck of the current product — discovers the aspects worth showing (the CLI's `--help`, the web app's routes, the library's quickstart), captures each with the *right tool per surface* (project's existing browser driver for web — Selenium-Java if none / Playwright for Node-Python / VHS for CLI / Freeze for code snippets), and assembles a captioned, narrative-ordered deck under `presentation/` ready to walk through in a meeting, paste into slides, or send to stakeholders. Use when the user asks for "presentation screenshots", "a demo deck", "screenshots for a slide deck", "show what this does", "presentation of the product", or is preparing to demo/pitch the project. Works on CLIs, web apps, libraries, and TUIs.
---

# Screenshot Tour

> **Try it:** `/screenshot-tour:screenshot-tour` — or say "build a presentation deck of this product".

A *presentation deck* is not a screenshot — it's the **set of aspects** a stranger needs to see to understand what the product does, ordered as a narrative they can follow without you talking over it. A single capture answers "what does it look like"; a deck answers "what does it do, end to end, in the moments that matter." The skill's job is to make sure the deck is **complete enough** to substitute for a 5-minute live demo, and **consistent enough** that every image reads as one product.

The deliverable is the deck itself — a numbered set of images plus a one-page manifest under `presentation/`. Slide-deck export, README integration, and docs-site embedding are *optional follow-ups* (see the bottom of this file), not part of the core loop.

## When to invoke

Trigger phrases:
- "build a presentation of this", "presentation deck", "demo deck", "presentation screenshots"
- "screenshots for the slide deck", "slide-ready screenshots", "screenshots for the meeting"
- "show what this does", "demo this product", "walk through the product"
- "I need to present this", "pitch screenshots", "before/after captures of the feature"

Also invoke proactively when the user is preparing for a demo, a stakeholder meeting, a release announcement, or a pitch and there are no captures in `presentation/`.

Don't invoke for single ad-hoc screenshots (use a generic screenshot skill or `Bash` directly), for visual regression testing (use Chromatic / Playwright tests), or for documentation-site illustrations (that's a downstream consumer, not the goal of this skill).

## Files this skill owns

- `presentation/plan.md` — the editable tour plan (numbered aspects + capture method per aspect); user-gated before any capture runs.
- `presentation/tour.md` — the final manifest with each image + caption, ordered for narrative.
- `presentation/recipes/*.tape` (CLI products) or `*.spec.ts` (web products) — the per-aspect capture scripts. Re-runnable.
- `presentation/NN-<slug>.{png,gif}` — the captures themselves, numbered for ordering.
- `presentation/contact-sheet.png` — optional 1-image overview of the whole deck (5×N grid).
- `.claude/screenshot-tour/log.md` — the per-run log (one entry per tour run); the skill graduates patterns out of this into a `## Screenshot tour` block in the repo's `CLAUDE.md`.

The shipped `log.md` in this plugin is a read-only seed; the live, append-only log lives at the consuming repo's `.claude/screenshot-tour/log.md`.

## The three phases

### 1. Discover — propose the tour plan

Read the repo and propose 5–12 aspects worth capturing. **Don't capture anything yet.** Sources, in order:

1. **README** — the *promised* aspects. If the README has a "Features" section, every bullet is a candidate. The hero animation/screenshot (if any) tells you the headline framing.
2. **Entry points** — for CLIs, the binary's `--help` (top-level + per-subcommand `--help`); for web apps, the route table (Spring `RequestMapping`, Next/Remix `pages/`, Django `urls.py`, etc.); for libraries, the public API surface in the entry module + example/sample/quickstart files.
3. **`docs/`** — if there's a docs site, its top-level nav is the canonical list of aspects.
4. **What the audit is asking for** — if `evolving-claude-md` has surfaced any "graduated to Conventions" patterns, those are usually load-bearing aspects.
5. **Recent CHANGELOG / git log** — last 1–2 releases tell you what's *new* and worth foregrounding.

Write `presentation/plan.md` with this shape:

```markdown
# Screenshot tour plan — <product>

> Edit freely before approving. Each aspect = one image. Reorder for narrative; cut anything that won't read in a 30-second skim of the deck.

## Aspects

1. **hero** — opening shot (`<what it shows>`) — *capture: VHS / Playwright / Freeze / manual*
2. **install** — install command + first run output — *capture: VHS*
3. **<feature-1>** — `<one-line caption that will appear under the image>` — *capture: <method>*
...
N. **outcome** — the payoff (a chart, a digest, a finished workflow) — *capture: <method>*

## Capture defaults
- product-type: <cli | web | library | tui | mixed>
- dimensions: <e.g. 1200×800 for web; 1200×720 for VHS>
- theme: <e.g. Dracula for VHS; system-light for web>
- output dir: presentation/
```

**Stop and ask the user to confirm the plan before phase 2.** A 12-aspect tour costs real time to capture; the cheapest way to throw work away is to capture the wrong aspects.

### 2. Capture — execute the plan, one aspect at a time

For each aspect in `plan.md`, run the matching capture method. Each method ships its own recipe file under `presentation/recipes/` so the tour is re-runnable on the next release.

**Use the right tool per surface.** Don't try to screenshot a web app with VHS or a terminal session with Playwright.

#### CLI / TUI → VHS (Charmbracelet)

The standard for terminal demos. Tape-file syntax → PNG / GIF / MP4. Renders text with a fixed-width font and known cell width, so column alignment survives.

Install: `go install github.com/charmbracelet/vhs@latest` (also brew, scoop, nix, apt). Requires `ttyd` + `ffmpeg` in `$PATH`.

Minimal tape file (`presentation/recipes/02-install.tape`):

```
Output ../02-install.png
Require myproduct
Set FontSize 18
Set Width 1200
Set Height 720
Set Theme "Dracula"

Type "myproduct install"
Sleep 200ms
Enter
Sleep 2s
Screenshot ../02-install.png
```

Then: `vhs presentation/recipes/02-install.tape`.

For animated aspects (a multi-step demo worth as a GIF, not a still): change `Output ../02-install.gif` and drop the explicit `Screenshot` call (VHS records the whole run).

Cheat sheet of useful tape commands: `Type "..."`, `Enter [n]`, `Sleep <dur>`, `Ctrl+C`, `Backspace [n]`, `Tab`, `Hide` / `Show` (toggle recording mid-tape), `Set TypingSpeed 50ms`, `Set PlaybackSpeed 2`. Full reference: <https://github.com/charmbracelet/vhs>.

#### Web app → use the browser-driver your project already uses

**Don't introduce a new automation stack just to take screenshots.** A second driver in the repo is a maintenance liability and the recipes will rot the moment nobody runs them between releases. The right tool is the one your existing test suite already uses; the skill ships recipes for the three common cases.

##### Selenium / Selenide (Java / Kotlin / JVM)

Default for Java projects. If the repo already has Selenium WebDriver, Selenide, or Playwright-Java as a test dependency, reuse it. Reuses the project's WebDriverManager, browser, and viewport conventions; recipes land in `src/test/java/.../screenshots/` so the build runs them.

Minimal recipe (`src/test/java/.../screenshots/DashboardTourTest.java`):

```java
@Test
void dashboard() throws IOException {
    var dim = new Dimension(1440, 900);
    driver.manage().window().setSize(dim);
    driver.get(System.getenv().getOrDefault("BASE_URL", "http://localhost:8080"));
    driver.findElement(By.linkText("Dashboard")).click();
    new WebDriverWait(driver, Duration.ofSeconds(10))
        .until(d -> ((JavascriptExecutor)d).executeScript(
            "return document.readyState").equals("complete"));
    var png = ((TakesScreenshot) driver).getScreenshotAs(OutputType.FILE);
    Files.copy(png.toPath(), Path.of("presentation/03-dashboard.png"),
               REPLACE_EXISTING);
}
```

Selenide variant (shorter): `Selenide.screenshot(OutputType.FILE)` returns the file directly, no `TakesScreenshot` cast.

Full-page captures: Selenium's `getScreenshotAs` is viewport-only. For full-page on Chrome/Edge use the CDP command:

```java
var screenshot = ((HasCdp) driver).executeCdpCommand(
    "Page.captureScreenshot", Map.of("captureBeyondViewport", true));
Files.write(Path.of("presentation/03-dashboard.png"),
            Base64.getDecoder().decode((String) screenshot.get("data")));
```

Tips:
- One JUnit test class per aspect (`DashboardTourTest`, `SettingsTourTest`, …) — a failure in aspect 7 should not block aspects 8–12.
- Annotate the tour class with `@Tag("screenshots")` and gate it from CI by default (`-DexcludedGroups=screenshots`) — you want to *run* them on release prep, not on every PR.
- Pin viewport in `@BeforeAll` so the whole deck shares dimensions.
- For demo data, seed via the app's normal API in `@BeforeAll` so the deck doesn't drift session-to-session.

##### Playwright (Node / Python — optional)

Use if the project's test stack is already Node/Python or you genuinely need cross-browser (Chromium + Firefox + WebKit) coverage. Playwright's `screenshot({fullPage: true})` handles full-page natively (no CDP gymnastics) and the action vocabulary (click/type/hover/select_option/press_key/drag/wait/navigate/evaluate/fill_form/handle_dialog/file_upload/resize/hide) is the richest for scripted tours.

Install (Node): `npm i -D @playwright/test && npx playwright install chromium`. Python: `pip install playwright && playwright install chromium`. Java has `Playwright-Java` if you want the action vocab without leaving the JVM.

```typescript
import { test } from '@playwright/test';

test('dashboard', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(process.env.BASE_URL ?? 'http://localhost:3000');
  await page.getByRole('link', { name: 'Dashboard' }).click();
  await page.waitForLoadState('networkidle');
  await page.screenshot({
    path: 'presentation/03-dashboard.png',
    fullPage: true,
  });
});
```

##### Cypress / WebDriverIO / TestCafe / shot-scraper / etc.

If that's what the repo uses, use that. Cypress: `cy.screenshot('03-dashboard', {capture: 'fullPage'})`. WDIO: `browser.saveFullPageScreenshot(...)`. [`shot-scraper`](https://shot-scraper.datasette.io/) (Python, Playwright-backed) is the lightest-weight option for one-off captures without a test framework. The skill's contract is "one recipe per aspect, numbered, lands in `presentation/`" — *how* the recipe runs is up to the project.

##### Selection rule

1. Project already has a browser driver in `pom.xml` / `package.json` / `requirements.txt` → use that.
2. No existing driver, but it's a Java repo → Selenium-Java + Selenide (matches the wider ecosystem).
3. No existing driver, Node/Python repo → Playwright (best DX for fresh installs).
4. No existing driver, one-off capture only → `shot-scraper` (zero project footprint).

#### Code snippet / config / output → Freeze (Charmbracelet)

For aspects where the value *is* the code (a config file, an API call, a CLI output transcript), pretty-print to PNG with window chrome.

Install: `go install github.com/charmbracelet/freeze@latest` (also brew, scoop, nix). Pure static — no runtime, no terminal needed.

```
freeze --language=yaml \
       --theme=github \
       --window \
       --output presentation/05-config.png \
       config/application.yml
```

Or pipe live: `myproduct analyze --hints | freeze --language=ansi -o presentation/06-hints.png`.

Carbon (<https://carbon.now.sh>) and Ray.so are browser alternatives — use Freeze for scripted/reproducible captures.

#### Manual (the fallback)

Some aspects only a human can capture cleanly — mobile UI, OS dialogs, hardware. Don't simulate them; write a one-paragraph checklist in `plan.md` ("open Settings → Profile, capture 1200×800") and the user supplies the file. Mark `*method: manual*` in the plan.

#### Format rules (apply across all methods)

- **PNG for stills** (no JPEG; JPEG artifacts murder small text). GIF/WEBM/MP4 for animated aspects only.
- **One consistent set of dimensions** per deck (e.g. all web shots 1440×900, all VHS shots 1200×720). The deck reading as *one product* matters more than each shot being perfectly tight.
- **Numbered prefixes** (`01-`, `02-`, …) so file order = deck order.
- **No dev clutter** — close DevTools, hide notification banners, clear test fixtures, mask secrets. The deck represents the product, not the dev environment.
- **Light theme by default** for screenshots in READMEs and docs (better print legibility); dark variants under `presentation/dark/` if needed.

### 3. Assemble — write the manifest + (optional) contact sheet

After capture, write `presentation/tour.md`:

```markdown
# <Product> — tour

A 30-second look at <product> across <N> aspects.

## 1. Hero
![hero](01-hero.gif)
<one-sentence what it does>

## 2. Install
![install](02-install.png)
<one-sentence install pitch>

...

## N. Outcome
![outcome](NN-outcome.png)
<one-sentence why it matters>

---
Generated by [screenshot-tour](https://alexmond.org/alexmskills/screenshot-tour.html). Re-run with `/screenshot-tour:screenshot-tour`.
```

**Order for narrative**, not for capture-method or alphabetical. A good order: *Hero → Install → 2–3 core flows → Advanced/outcome → What's next*.

**Contact sheet (optional)** — a single PNG with all captures laid out in a 5×N grid. Useful for slide-deck section openers. Generate via ImageMagick:

```bash
magick montage presentation/[0-9]*.png \
       -tile 5x -geometry 240x160+8+8 -background '#0e1117' \
       presentation/contact-sheet.png
```

## Quality bar — would this deck land?

Before finishing, gut-check the deck against three questions:

1. **Does the hero shot answer "what is this"?** If a reader skips everything else, they should know what the product does from image 1 alone.
2. **Could you swap any two adjacent images without losing the story?** If yes, the order is too arbitrary — re-narrate.
3. **Is anything *clearly* missing?** Walk the README's Features section and the `--help`/route table again. The audit step exists because the discovery phase always misses 1–2 aspects.

If any answer is "no", iterate on the *plan* (don't re-capture; re-design).

## Optional follow-ups (not run by default)

The deck under `presentation/` is the deliverable. These are **opt-in** consumers — only do them when the user asks.

- **Slide-deck export** — re-package the deck as a Keynote / PowerPoint / Google Slides / Reveal.js / Marp slide per aspect, with each caption as the speaker note. Closest to the skill's intended use; one-line CLI for Reveal.js / Marp from the manifest. Reach for this first when the user says "I'm presenting Friday."
- **README integration** *(later)* — propose a README diff that adds the hero image + a `See full tour →` link to `presentation/tour.md`. Skip unless the user asks for it.
- **Antora / docs-site page** *(later)* — render the deck as a docs-site page under the project's docs component. Skip unless the user asks for it.

Don't auto-run any of these.

## What goes into `## Screenshot tour` in the repo's CLAUDE.md (graduation)

After 2–3 successful runs in the same repo, lift the stable bits into a `## Screenshot tour` block in `CLAUDE.md` so the next run starts there:

```markdown
## Screenshot tour
- product-type: cli + library
- standard dimensions: 1200×720 (VHS), 1000×600 (Freeze)
- theme: Dracula (VHS), GitHub Light (Freeze)
- output dir: presentation/
- standard recipes: presentation/recipes/*.tape (re-runnable)
- canonical aspects (always capture): hero, install, <feature-1>, <feature-2>, outcome
```

Graduated entries are pruned from `.claude/screenshot-tour/log.md` (the log keeps the *variance*, the block keeps the *invariants*).

## The per-run log

Append one entry per tour run to `.claude/screenshot-tour/log.md`:

```
## <run-id>  <yyyy-mm-dd>  <repo>
- product-type: <cli | web | library | tui | mixed>
- aspects-planned: <n>   aspects-captured: <m>   aspects-fallback: <k>
- tools-used: <vhs (n), playwright (m), freeze (k), manual (j)>
- gotchas: <e.g. `ttyd` missing in container; Playwright headless DPR=1 too small; VHS wayland incompatibility>
- steering: <what the user edited in the plan — added X, cut Y, reframed Z>
- outcome: <committed-at <path> | partial | abandoned>
- graduated: <what lifted to the `## Screenshot tour` block this run, if any>
```

The log is how the skill *learns*. After 3 runs in the same repo: stable capture methods graduate to the CLAUDE.md block; failed methods get a `do-not-try` note; the canonical-aspects list grows.

## Common failure modes (read before running)

- **Skipping the plan-confirmation gate.** Capturing first, narrating after, makes the deck a collection of pretty images that don't tell a story. The plan is the deck; the captures are the body.
- **Mixing capture mechanisms within one frame.** Don't paste a VHS PNG next to a Playwright PNG with mismatched padding/borders — the deck stops reading as one product. Pick per *deck*, not per *aspect*.
- **Animated GIFs for everything.** A GIF for the hero is great; 12 GIFs in a README is unreadable. Default to PNG; reach for GIF/MP4 only when motion is the point.
- **No light/dark consistency.** Pick one and stick with it across the deck.
- **Secrets in screenshots.** API keys, tokens, real customer data. Always run a pass that masks before committing. The skill should remind the user before capture starts.
- **No `Require` lines in VHS tapes.** A tape that runs against a stale `$PATH` silently captures the wrong product version. Always declare what binaries the tape depends on.
- **One huge spec file for Playwright.** Splits the deck into per-aspect spec files — a failure in aspect 7 should not block aspects 8–12.

## Provenance & inspiration

This skill's capture strategies stand on:
- **Charmbracelet VHS** — <https://github.com/charmbracelet/vhs> (CLI tape recordings)
- **Charmbracelet Freeze** — <https://github.com/charmbracelet/freeze> (code/output stills)
- **Playwright** — <https://playwright.dev> (web tours)
- **Carbon** — <https://carbon.now.sh> (pretty code, browser alternative)
- **awesome-readme** — <https://github.com/matiassingers/awesome-readme> (README conventions)

The *tour* layer (discovery → plan → capture → assemble → graduate) is original to this skill.
