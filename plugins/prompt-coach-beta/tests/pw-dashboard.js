#!/usr/bin/env node
/*
 * Playwright UI test for the prompt-coach dashboard (scripts/serve.py).
 *
 * Self-contained: it finds a free port, spawns serve.py against a THROWAWAY
 * repo dir (so it never touches your real config), drives the four pages, and
 * asserts layout invariants that plain unit tests can't see — page routing,
 * the level TOC, object sub-field alignment, and the Save-button column.
 *
 *   node plugins/prompt-coach-beta/tests/pw-dashboard.js
 *   PC_PW_OUT=/tmp/shots node .../pw-dashboard.js   # also write screenshots
 *
 * Playwright is an OPTIONAL dev dependency (the plugin itself is stdlib-only).
 * If it can't be resolved, this test SKIPS (exit 0) rather than failing — set
 * NODE_PATH to your Playwright install, e.g.
 *   export NODE_PATH="$HOME/.local/lib/playwright/node_modules"
 */
'use strict';
const { spawn } = require('child_process');
const http = require('http');
const net = require('net');
const os = require('os');
const fs = require('fs');
const path = require('path');

let chromium;
try { ({ chromium } = require('playwright')); }
catch (e) {
  console.log('· playwright not resolvable — skipping dashboard UI test (set NODE_PATH). SKIP');
  process.exit(0);
}

const SERVE = path.join(__dirname, '..', 'scripts', 'serve.py');
const OUT = process.env.PC_PW_OUT || null;
const results = [];
const ok = (name, pass, detail = '') => {
  results.push(pass); console.log(`${pass ? '✓' : '✗'} ${name}${detail ? '  — ' + detail : ''}`);
};
const freePort = () => new Promise(res => {
  const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); });
});
const waitUp = (base, ms = 10000) => new Promise((res, rej) => {
  const t0 = Date.now();
  const tick = () => http.get(base + '/', r => { r.resume(); res(); })
    .on('error', () => (Date.now() - t0 > ms ? rej(new Error('server did not start')) : setTimeout(tick, 150)));
  tick();
});

(async () => {
  const port = await freePort();
  const base = `http://127.0.0.1:${port}`;
  const repo = fs.mkdtempSync(path.join(os.tmpdir(), 'pc-pw-'));
  const srv = spawn('python3', [SERVE, '--cwd', repo, '--port', String(port)], { stdio: 'ignore' });
  let browser;
  try {
    await waitUp(base);
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const errors = [];
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
    page.on('pageerror', e => errors.push(String(e)));

    const pages = [
      ['stats', '.tiles', 'Stats'], ['mastery', '.rule', 'Mastery'],
      ['config', '.cfg .k', 'Config'], ['options', '#options', 'Options'],
    ];
    for (const [hash, sel, label] of pages) {
      await page.goto(`${base}/#${hash}`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(200);
      const vis = await page.locator(`section[data-page="${hash}"].active ${sel}`).first().isVisible().catch(() => false);
      ok(`page ${label} renders`, vis);
      const navOn = (await page.locator('#nav button.on').innerText()).trim();
      ok(`toolbar highlights ${label}`, navOn === label, `active=${navOn}`);
      if (OUT) await page.screenshot({ path: path.join(OUT, `pw-${hash}.png`), fullPage: true });
    }

    await page.goto(`${base}/#mastery`, { waitUntil: 'networkidle' });
    ok('mastery level TOC present', (await page.locator('#toc a').count()) >= 5);

    // object sub-fields vertically aligned (the reported bug)
    await page.goto(`${base}/#config`, { waitUntil: 'networkidle' });
    await page.locator('#catnav button', { hasText: /^llm-fallback$/ }).click();
    await page.waitForTimeout(150);
    const centers = [];
    for (const id of ['cfg_llm_fallback__enabled', 'cfg_llm_fallback__model', 'cfg_llm_fallback__min_words']) {
      const b = await page.locator('#' + id).boundingBox(); centers.push(b ? b.y + b.height / 2 : null);
    }
    const spread = Math.max(...centers) - Math.min(...centers);
    ok('obj sub-fields vertically aligned', centers.every(Boolean) && spread <= 3, `spread ${spread.toFixed(1)}px`);

    // Save buttons share one right-aligned column
    await page.locator('#catnav button', { hasText: /^all$/ }).click();
    await page.waitForTimeout(150);
    const xs = [];
    for (const s of await page.locator('.acts button:has-text("Save")').all()) {
      const b = await s.boundingBox(); if (b) xs.push(Math.round(b.x));
    }
    const xSpread = xs.length ? Math.max(...xs) - Math.min(...xs) : 999;
    ok('Save buttons aligned in one column', xs.length > 3 && xSpread <= 2, `${xs.length} rows, spread ${xSpread}px`);

    ok('no console/page errors', errors.length === 0, errors.slice(0, 2).join(' | '));
  } catch (e) {
    ok('test run completed', false, String(e && e.message || e));
  } finally {
    if (browser) await browser.close();
    srv.kill();
    try { fs.rmSync(repo, { recursive: true, force: true }); } catch (_) {}
  }

  const passed = results.filter(Boolean).length;
  console.log(`\n${passed}/${results.length} checks passed`);
  process.exit(passed === results.length && results.length > 0 ? 0 : 1);
})();
