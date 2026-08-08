#!/usr/bin/env node
/* UI test for the mindmap-prompt canvas — capture flow end to end.
 *
 * Optional: skips (exit 0) when Playwright isn't installed, same as the
 * prompt-coach dashboard test. Uses the account-wide Playwright, never a
 * project-local one.
 *
 *   node plugins/mindmap-prompt/tests/pw-canvas.js
 */
"use strict";

const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

let chromium;
try {
  ({ chromium } = require("playwright"));
} catch {
  console.log("  · playwright not installed — skipping canvas UI test");
  process.exit(0);
}

const HERE = __dirname;
const SERVE = path.join(HERE, "..", "scripts", "serve.py");
const PORT = 8779;
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
  const repo = fs.mkdtempSync(path.join(os.tmpdir(), "mm-ui-"));
  const srv = spawn("python3", [SERVE, "--port", String(PORT), "--cwd", repo, "--no-open"],
    { stdio: "ignore" });
  const stop = () => { try { srv.kill(); } catch {} };
  process.on("exit", stop);

  // wait for the port
  for (let i = 0; i < 50; i++) {
    try { await fetch(BASE); break; } catch { await new Promise((r) => setTimeout(r, 100)); }
  }

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

  try {
    await page.goto(BASE, { waitUntil: "domcontentloaded" });
    check("page loads", await page.title() === "mindmap-prompt");

    // --- a fresh map opens with a seeded root, ready to type over -----------
    await page.waitForSelector(".node.editing", { timeout: 3000 });
    check("a fresh map seeds one root node, already in edit mode",
      (await page.locator(".node").count()) === 1 &&
      (await page.locator(".node.k-goal").count()) === 1);

    await page.keyboard.press("Control+a");        // typing replaces "Main idea"
    await page.keyboard.type("Ship dark mode");
    await page.keyboard.down("Shift"); await page.keyboard.press("Enter");
    await page.keyboard.press("Enter"); await page.keyboard.up("Shift");
    await page.keyboard.type("Done = every page passes contrast checks.");
    await page.keyboard.press("Escape");

    // --- a stray click on empty canvas must NOT make a node ----------------
    await page.mouse.click(1100, 700);
    await page.waitForTimeout(150);
    check("clicking empty canvas deselects instead of creating a node",
      (await page.locator(".node").count()) === 1);

    // --- the ⊕ control adds a child on the side you clicked ----------------
    await page.locator(".node.d0").hover();
    await page.locator(".node.d0 .plug.r").click();
    await page.waitForSelector(".node.editing");
    await page.keyboard.type("Right branch");
    await page.keyboard.press("Escape");
    const rightX = await page.locator(".node").last().evaluate((e) => e.offsetLeft);
    const rootX = await page.locator(".node.d0").evaluate((e) => e.offsetLeft);
    check("⊕ adds a child, and the right ⊕ places it to the right",
      (await page.locator(".node").count()) === 2 && rightX > rootX,
      `root=${rootX} child=${rightX}`);

    await page.locator(".node.d0").hover();
    await page.locator(".node.d0 .plug.l").click();
    await page.waitForSelector(".node.editing");
    await page.keyboard.type("Left branch");
    await page.keyboard.press("Escape");
    const leftX = await page.locator(".node").last().evaluate((e) => e.offsetLeft);
    check("the left ⊕ grows the map in the other direction",
      (await page.locator(".node").count()) === 3 && leftX < rootX,
      `root=${rootX} left=${leftX}`);

    // --- how do you edit an existing node? --------------------------------
    // Every path below was reachable in code but invisible on screen, and a
    // first-time user reported the boxes looked uneditable. The affordance is
    // the feature; assert it, not just the mechanism underneath.
    const left = page.locator(".node").last();      // still selected after Escape
    check("a selected node says how to edit itself",
      /just type|double-click/i.test(await left.locator(".tip").innerText()));

    await page.keyboard.type("Typed over");
    await page.waitForTimeout(120);
    check("typing over a selected node replaces its text",
      (await page.locator(".node.editing").count()) === 1 &&
      (await left.locator(".txt").innerText()).trim() === "Typed over",
      await left.locator(".txt").innerText());
    check("the editing node explains how to get out again",
      /Esc/i.test(await left.locator(".tip").innerText()));

    await page.keyboard.press("Escape");
    const lb = await left.boundingBox();
    await page.mouse.click(lb.x + lb.width / 2, lb.y + lb.height / 2);   // select
    await page.mouse.click(lb.x + lb.width / 2, lb.y + lb.height / 2);   // edit
    await page.waitForTimeout(150);
    check("clicking an already-selected node opens it for editing",
      (await page.locator(".node.editing").count()) === 1);
    await page.keyboard.press("Escape");


    // --- Tab commits and creates a connected child -------------------------
    await page.locator(".node.d0").click();       // select the root (no Escape:
    await page.keyboard.press("Tab");             // Escape would deselect it)
    await page.waitForSelector(".node.editing");
    await page.keyboard.type("Theme toggle");
    await page.keyboard.press("Escape");
    // Counting path elements isn't enough — a stale `stroke:none` once made every
    // connector invisible while the count stayed correct. Assert they actually draw.
    const strokes = await page.locator("#g-edges path").evaluateAll((ps) =>
      ps.map((p) => {
        const cs = getComputedStyle(p);
        return { stroke: cs.stroke, width: parseFloat(cs.strokeWidth) };
      }));
    check("Tab commits and spawns a connected child, and connectors are visible",
      (await page.locator(".node").count()) === 4 && strokes.length === 3 &&
      strokes.every((s) => s.stroke !== "none" && s.width > 0),
      JSON.stringify(strokes));

    // --- Enter commits and creates a sibling -------------------------------
    await page.keyboard.press("Enter");        // enter edit on selection
    await page.keyboard.press("Escape");
    await page.keyboard.press("Tab");          // child of "Theme toggle"
    await page.waitForSelector(".node.editing");
    await page.keyboard.type("Persist in localStorage");
    await page.keyboard.press("Enter");        // commit + sibling
    await page.waitForSelector(".node.editing");
    await page.keyboard.type("Remember per device");
    await page.keyboard.press("Escape");
    check("Enter commits and spawns a sibling under the same parent",
      (await page.locator(".node").count()) === 6);

    // --- number keys set the kind -----------------------------------------
    await page.keyboard.press("4");
    check("number keys set the node kind (4 = constraint)",
      (await page.locator(".node.k-constraint").count()) === 1);
    await page.keyboard.press("3");   // back to idea so it stays in the body

    // --- compile via the server -------------------------------------------
    await page.click("#b-compile");
    await page.waitForFunction(() => document.querySelector("#md").textContent.length > 10,
      null, { timeout: 5000 });
    const md = await page.locator("#md").textContent();
    check("compile returns the prompt built by the Python compiler",
      md.startsWith("# Ship dark mode") &&
      md.includes("## Theme toggle") &&
      md.includes("### Persist in localStorage") &&
      md.includes("Done = every page passes contrast checks."),
      md.slice(0, 200));

    // --- save round-trips to a .canvas on disk -----------------------------
    await page.click("#b-save");
    await page.waitForFunction(() => document.querySelector("#status").textContent.includes("saved"),
      null, { timeout: 5000 });
    const saved = path.join(repo, ".claude", "mindmap", "map.canvas");
    const canvas = JSON.parse(fs.readFileSync(saved, "utf8"));
    check("save writes JSON Canvas (nodes + edges) into the repo",
      Array.isArray(canvas.nodes) && Array.isArray(canvas.edges) &&
      canvas.nodes.length === 6 && canvas.nodes.every((n) => n.type === "text") &&
      canvas.nodes.some((n) => /^#goal /.test(n.text)),
      JSON.stringify(canvas.nodes.map((n) => n.text)));

    // --- the compiler agrees with what the page saved ----------------------
    const cli = execFileSync("python3", [path.join(HERE, "..", "scripts", "mindmap.py"),
      "compile", saved], { encoding: "utf8" });
    check("headless CLI compiles the saved map identically", cli.trim() === md.trim(),
      `cli=${JSON.stringify(cli.slice(0, 80))} ui=${JSON.stringify(md.slice(0, 80))}`);

    // --- reload restores the map ------------------------------------------
    await page.goto(BASE + "?map=map", { waitUntil: "domcontentloaded" });
    await page.waitForSelector(".node");
    check("a saved map reopens from its URL",
      (await page.locator(".node").count()) === 6 &&
      (await page.locator(".node.k-goal").count()) === 1);

    fs.mkdirSync(path.join(HERE, "shots"), { recursive: true });
    await page.screenshot({ path: path.join(HERE, "shots", "canvas.png") });

    // --- the ✦ expander ----------------------------------------------------
    // /api/ai is stubbed: a real `claude -p` costs tokens and ~10s, and what
    // needs guarding here is the wiring, not the model. `make test-ai` runs the
    // same flow against the live CLI.
    let asked = null;
    await page.route("**/api/ai", async (route) => {
      asked = JSON.parse(route.request().postData() || "{}");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ mode: asked.mode, ideas: ["Stub one", "Stub two"], text: "Stub rewrite" }),
      });
    });

    await page.locator(".node.d1").first().click();      // reopening cleared the selection
    check("✦ is offered on a node when the claude CLI is present",
      await page.locator(".node.sel .spark").isVisible());
    await page.locator(".node.sel .spark").click();
    await page.waitForSelector("#ai.open", { timeout: 2000 });

    const panelBox = await page.locator("#ai").boundingBox();
    const nodeBox = await page.locator(".node.sel").boundingBox();
    check("the ✦ panel sits beside its node, never on top of it",
      panelBox.x >= nodeBox.x + nodeBox.width || panelBox.x + panelBox.width <= nodeBox.x,
      `node=${Math.round(nodeBox.x)}..${Math.round(nodeBox.x + nodeBox.width)} panel=${Math.round(panelBox.x)}`);

    const beforeAI = await page.locator(".node").count();
    await page.locator("#ai .acts button", { hasText: "Break into steps" }).click();
    await page.waitForSelector("#ai-out li", { timeout: 5000 });
    check("the map's goal and ancestry are sent as context, not just the node",
      asked && asked.context && asked.context.goal.startsWith("Ship dark mode") &&
      Array.isArray(asked.context.path) && asked.context.path.length > 0,
      JSON.stringify(asked && asked.context));
    check("ideas are previewed, and nothing reaches the map until you apply",
      (await page.locator("#ai-out li").count()) === 2 &&
      (await page.locator(".node").count()) === beforeAI);

    await page.locator("#ai-apply").click();
    await page.waitForTimeout(250);
    check("applying adds one connected node per idea",
      (await page.locator(".node").count()) === beforeAI + 2 &&
      (await page.locator(".node.orphan").count()) === 0);

    // an error from the CLI has to surface, not vanish into a spinner
    await page.unroute("**/api/ai");
    await page.route("**/api/ai", (route) =>
      route.fulfill({ status: 502, contentType: "text/plain", body: "claude exited 1: nope" }));
    await page.locator(".node").last().click();
    await page.locator(".node.sel .spark").click();
    await page.waitForSelector("#ai.open");
    await page.locator("#ai .acts button", { hasText: "Expand into ideas" }).click();
    await page.waitForFunction(() => /✗/.test(document.querySelector("#ai-out").textContent),
      null, { timeout: 5000 });
    check("a failed call shows the reason instead of hanging",
      /nope/.test(await page.locator("#ai-out").innerText()) &&
      !(await page.locator("#ai-apply").isVisible()));
    await page.unroute("**/api/ai");
    await page.locator("[data-close=ai]").click();

    const real = errors.filter((e) => !/502/.test(e));   // the ✦ failure case is deliberate
    check("no page errors", real.length === 0, real.slice(0, 3).join(" | "));
  } finally {
    await browser.close();
    stop();
    fs.rmSync(repo, { recursive: true, force: true });
  }

  console.log();
  if (fails.length) {
    console.log(`  ${fails.length} FAILED: ${fails.join(", ")}`);
    process.exit(1);
  }
  console.log("  ALL GREEN");
})().catch((e) => { console.error(e); process.exit(1); });
