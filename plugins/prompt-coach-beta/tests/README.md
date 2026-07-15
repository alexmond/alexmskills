# prompt-coach-beta tests

Two layers, deliberately separate by dependency weight:

## `scripts/test-harness.py` — the release gate (zero deps)

Pure-stdlib Python. Drives the real hook + config surface as subprocesses in
throwaway HOME/repo dirs. **Run on every release:**

```bash
make test-coach
```

This is the authoritative gate — the plugin ships stdlib-only, and so does its
core test.

## `tests/pw-dashboard.js` — optional UI test (needs Playwright)

Browser-driven layout test for the web dashboard (`scripts/serve.py`). It
catches things unit tests can't see: page routing, the level TOC, object
sub-field alignment, and the Save-button column. **Optional** — the dashboard is
a convenience surface, and Playwright is a heavier dep than the plugin's
stdlib-only ethos, so this is *not* part of `make test-coach`.

```bash
make test-dashboard          # spawns its own server on a free port, then asserts
PC_PW_OUT=/tmp/shots make test-dashboard   # also writes full-page screenshots
```

Self-contained: it finds a free port, launches `serve.py` against a throwaway
repo (never touches your real config), runs the checks, and tears everything
down. If Playwright isn't resolvable it **skips** (exit 0) rather than failing —
point `NODE_PATH` at your install to enable it:

```bash
export NODE_PATH="$HOME/.local/lib/playwright/node_modules"
```
