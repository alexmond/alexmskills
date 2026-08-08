#!/usr/bin/env node
/* Live smoke test for the ✦ expander — `make test-ai`.
 *
 * Deliberately NOT part of `make test-canvas`: this one really shells out to
 * `claude -p`, so it costs tokens and tens of seconds. test-canvas stubs
 * /api/ai and covers the wiring; this covers the thing the stub can't — that a
 * real model reply survives the round trip and lands on the map.
 *
 * Skips cleanly (rc 0) when playwright or the claude CLI is missing, so it can
 * sit in a Makefile without becoming a tripwire.
 */
"use strict";

const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

let chromium;
try {
  ({ chromium } = require("playwright"));
} catch {
  console.log("  · playwright not installed — skipping the ✦ live test");
  process.exit(0);
}
if (spawnSync("which", ["claude"]).status !== 0) {
  console.log("  · the claude CLI is not on PATH — skipping the ✦ live test");
  process.exit(0);
}

const HERE = __dirname;
const SERVE = path.join(HERE, "..", "scripts", "serve.py");
const PORT = 8778;
const BASE = `http://127.0.0.1:${PORT}/`;

const fails = [];
function check(name, ok, detail = "") {
  console.log(`  ${ok ? "✓" : "✗"} ${name}`);
  if (!ok) {
    fails.push(name);
    if (detail) console.log(`      ${detail}`);
  }
}

(async () => {
  const repo = fs.mkdtempSync(path.join(os.tmpdir(), "mm-ai-"));
  const srv = spawn("python3", [SERVE, "--cwd", repo, "--port", String(PORT), "--no-open"],
    { stdio: "ignore" });
  const stop = () => { try { srv.kill(); } catch {} };
  process.on("exit", stop);

  for (let i = 0; i < 60; i++) {
    try { await fetch(BASE); break; } catch { await new Promise((r) => setTimeout(r, 100)); }
  }

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));

  try {
    await page.goto(BASE, { waitUntil: "domcontentloaded" });
    await page.waitForSelector(".node.editing", { timeout: 3000 });
    await page.keyboard.press("Control+a");
    await page.keyboard.type("Ship dark mode");
    await page.keyboard.press("Tab");
    await page.keyboard.type("Theme toggle");
    await page.keyboard.press("Escape");

    check("the server reports the claude CLI as available",
      (await (await fetch(BASE + "api/caps")).json()).ai === true);

    // --- expand, for real --------------------------------------------------
    const before = await page.locator(".node").count();
    await page.locator(".node.sel .spark").click();
    await page.waitForSelector("#ai.open");
    await page.locator("#ai .acts button", { hasText: "Break into steps" }).click();
    await page.waitForFunction(
      () => !/thinking/.test(document.querySelector("#ai-out").textContent),
      null, { timeout: 240000 });

    const shown = await page.locator("#ai-out").innerText();
    const ideas = await page.locator("#ai-out li").count();
    check("claude -p returns usable ideas", ideas >= 2, shown.slice(0, 200));
    if (!ideas) throw new Error("no ideas to apply: " + shown.slice(0, 300));

    await page.locator("#ai-apply").click();
    await page.waitForTimeout(400);
    check("applying wires every idea into the map",
      (await page.locator(".node").count()) === before + ideas &&
      (await page.locator(".node.orphan").count()) === 0);

    // --- the real proof: they survive the compiler -------------------------
    await page.click("#b-compile");
    await page.waitForFunction(
      () => document.querySelector("#md").textContent.length > 10, null, { timeout: 8000 });
    const md = await page.locator("#md").textContent();
    const added = await page.evaluate(() => [...document.querySelectorAll(".node")]
      .map((n) => n.querySelector(".cap").textContent).slice(2));
    check("every AI-added idea reaches the compiled prompt",
      added.length > 0 && added.every((t) => md.includes(t)),
      added.filter((t) => !md.includes(t)).join(" | "));

    // --- rewrite, for real -------------------------------------------------
    await page.locator(".node.d0").click();
    await page.locator(".node.sel .spark").click();
    await page.waitForSelector("#ai.open");
    const wasText = await page.locator(".node.d0 .cap").innerText();
    await page.locator("#ai .acts button", { hasText: "Add done-criteria" }).click();
    await page.waitForFunction(
      () => !/thinking/.test(document.querySelector("#ai-out").textContent),
      null, { timeout: 240000 });
    await page.locator("#ai-apply").click();
    await page.waitForTimeout(300);
    const nowText = await page.locator(".node.d0 .cap").innerText();
    check("a rewrite replaces the node's text and adds no nodes",
      nowText !== wasText && (await page.locator(".node").count()) === before + ideas,
      `"${wasText}" -> "${nowText}"`);

    check("no page errors", errors.length === 0, errors.slice(0, 3).join(" | "));
  } catch (err) {
    check("live ✦ run completed", false, String(err && err.message || err));
  } finally {
    await browser.close();
    stop();
    fs.rmSync(repo, { recursive: true, force: true });
  }

  console.log(fails.length ? `\n  ${fails.length} FAILED: ${fails.join(", ")}\n` : "\n  ALL GREEN\n");
  process.exit(fails.length ? 1 : 0);
})();
