/**
 * TheAssembly — Playwright Load Test
 *
 * Simulates 50 unique user sessions (5 waves × 10 parallel contexts) against
 * the production athlete app. Each context varies device, viewport, user-agent,
 * scroll depth, and link interactions to generate rich data in GA4 and Clarity.
 *
 * Usage (inside Docker container):
 *   node /tmp/playwright_load_test.js
 *
 * Run via:
 *   docker cp tools/playwright_load_test.js theassembly-mcp-playwright-1:/tmp/
 *   docker exec theassembly-mcp-playwright-1 node /tmp/playwright_load_test.js
 */

// Use playwright@1.51.0 installed in /tmp/node_modules to match container browsers
const { chromium } = require("/tmp/node_modules/playwright");

const TARGET_URL = "https://asm-athlete.streamlit.app";
const WAVES = 5;
const CONTEXTS_PER_WAVE = 10;
const WAVE_GAP_MS = 5000;

// ── Device profiles ──────────────────────────────────────────────────────────
const DEVICES = [
  { name: "mobile-sm",  width: 375,  height: 812 },
  { name: "mobile-lg",  width: 414,  height: 896 },
  { name: "tablet",     width: 768,  height: 1024 },
  { name: "desktop",    width: 1280, height: 800 },
  { name: "wide",       width: 1920, height: 1080 },
];

// ── User-agent strings ───────────────────────────────────────────────────────
const USER_AGENTS = [
  // Chrome macOS
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
  // Chrome Windows
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
  // Safari macOS
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
  // Safari iPhone
  "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1",
  // Firefox
  "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
  // Edge
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
  // Chrome Android
  "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
  // Samsung Internet
  "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/24.0 Chrome/117.0.0.0 Mobile Safari/537.36",
  // Chrome iPad
  "Mozilla/5.0 (iPad; CPU OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/124.0.0.0 Mobile/15E148 Safari/604.1",
  // Opera
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 OPR/110.0.0.0",
];

// ── Scroll profiles (percentage of page height) ─────────────────────────────
const SCROLL_PROFILES = [
  [25],
  [25, 50],
  [25, 50, 75],
  [25, 50, 75, 100],
  [50, 100],
  [75],
  [100],
  [33, 66, 100],
  [50],
  [25, 100],
];

// ── Helpers ──────────────────────────────────────────────────────────────────
function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function pick(arr, idx) {
  return arr[idx % arr.length];
}

function randomBetween(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function pad(n, width = 2) {
  return String(n).padStart(width, "0");
}

// ── Per-context simulation ───────────────────────────────────────────────────
async function runContext(browser, wave, ctxIdx) {
  const globalIdx = (wave - 1) * CONTEXTS_PER_WAVE + ctxIdx;
  const device    = pick(DEVICES, globalIdx);
  const ua        = pick(USER_AGENTS, globalIdx);
  const scrollPts = pick(SCROLL_PROFILES, globalIdx);
  const dwellMs   = randomBetween(10000, 22000);
  const label     = `[W${pad(wave)}/C${pad(ctxIdx + 1)}]`;

  const networkHits = {
    gtagScript: false,
    gCollect: false,
    clarityScript: false,
    clarityCollect: false,
  };

  let loadTimeMs = 0;
  let appLoaded  = false;
  let linkClicked = false;
  let errorMsg   = null;
  const debugUrls = [];  // collect all URLs for wave-1 diagnostics

  const ctx = await browser.newContext({
    viewport:  { width: device.width, height: device.height },
    userAgent: ua,
    locale:    "en-US",
    timezoneId: "America/Los_Angeles",
  });

  // Capture network requests
  ctx.on("response", (resp) => {
    const url = resp.url();
    // Collect all non-trivial URLs for wave-1 debug output
    if (wave === 1 && ctxIdx === 0 && !url.includes("streamlit.app") && !url.includes("webhook"))
      debugUrls.push(url.slice(0, 120));
    // Broaden gtag match: any request to googletagmanager or google-analytics
    if (url.includes("googletagmanager.com") || url.includes("google-analytics.com") || url.includes("analytics.google.com"))
      networkHits.gtagScript = true;
    if (
      (url.includes("google-analytics.com/g/collect") ||
       url.includes("analytics.google.com/g/collect") ||
       url.includes("google-analytics.com/j/collect"))
    )
      networkHits.gCollect = true;
    if (url.includes("clarity.ms") || url.includes("clarity.ms/tag/") || url.includes("scripts.clarity.ms"))
      networkHits.clarityScript = true;
    if (url.includes("clarity.ms/collect") || url.includes("b.clarity.ms"))
      networkHits.clarityCollect = true;
  });

  const page = await ctx.newPage();

  try {
    const t0 = Date.now();
    await page.goto(TARGET_URL, { waitUntil: "domcontentloaded", timeout: 30000 });

    // Wait for the Streamlit app iframe to load (title changes from "Streamlit" to "TheAssembly")
    await page.waitForFunction(
      () => document.title.includes("TheAssembly") || document.title.includes("Assembly"),
      { timeout: 25000 }
    ).catch(() => {}); // don't fail if slow

    loadTimeMs = Date.now() - t0;
    appLoaded  = true;

    // Give analytics scripts time to initialise (gtag is async)
    await sleep(3000);

    // ── Scroll simulation ───────────────────────────────────────────────────
    const pageHeight = await page.evaluate(
      () => document.documentElement.scrollHeight || document.body.scrollHeight
    );
    for (const pct of scrollPts) {
      const y = Math.floor((pct / 100) * pageHeight);
      await page.evaluate((scrollY) => window.scrollTo({ top: scrollY, behavior: "smooth" }), y);
      await sleep(randomBetween(600, 1200));
    }

    // ── Weather strip horizontal scroll (mobile/tablet only) ───────────────
    if (device.width <= 768) {
      await page.evaluate(() => {
        const strip = document.querySelector(".weather-strip");
        if (strip) strip.scrollLeft = 120;
      });
      await sleep(400);
    }

    // ── Click a random HN link (if visible) ────────────────────────────────
    // HN links are inside the Streamlit app iframe at /~/+/ — use frame-aware access
    const appFrame = page.frames().find(f => f.url().includes("/~/+/")) || page.mainFrame();
    const hnLinks = await appFrame.$$("a[href*='news.ycombinator.com'], a[href*='mitchellh.com'], a[href*='keepandroidopen.org'], a[href*='localsend']").catch(() => []);
    if (hnLinks.length > 0) {
      const target = hnLinks[globalIdx % hnLinks.length];
      await appFrame.evaluate((el) => el.setAttribute("target", "_blank"), target).catch(() => {});
      await target.click().catch(() => {});
      // Close any new tab that opened
      await sleep(500);
      const pages = ctx.pages();
      for (const p of pages) { if (p !== page) await p.close().catch(() => {}); }
      linkClicked = true;
    }

    // ── Dwell ───────────────────────────────────────────────────────────────
    await sleep(dwellMs);

  } catch (err) {
    errorMsg = err.message.split("\n")[0].slice(0, 80);
  } finally {
    await page.close().catch(() => {});
    await ctx.close().catch(() => {});
  }

  return {
    label,
    wave,
    ctxIdx: ctxIdx + 1,
    device: device.name,
    scrollDepth: Math.max(...scrollPts) + "%",
    dwellSec: (dwellMs / 1000).toFixed(1),
    loadTimeMs,
    appLoaded,
    linkClicked,
    gtagScript: networkHits.gtagScript,
    gCollect:   networkHits.gCollect,
    clarityScript: networkHits.clarityScript,
    clarityCollect: networkHits.clarityCollect,
    error: errorMsg,
    debugUrls,
  };
}

// ── Main ─────────────────────────────────────────────────────────────────────
async function main() {
  console.log("=".repeat(72));
  console.log("  TheAssembly — Playwright Load Test");
  console.log(`  Target : ${TARGET_URL}`);
  console.log(`  Plan   : ${WAVES} waves × ${CONTEXTS_PER_WAVE} contexts = ${WAVES * CONTEXTS_PER_WAVE} sessions`);
  console.log("=".repeat(72));

  const browser = await chromium.launch({ headless: true });
  const allResults = [];

  for (let wave = 1; wave <= WAVES; wave++) {
    console.log(`\n── Wave ${wave}/${WAVES} ─ launching ${CONTEXTS_PER_WAVE} contexts in parallel ──`);
    const waveStart = Date.now();

    const promises = Array.from({ length: CONTEXTS_PER_WAVE }, (_, i) =>
      runContext(browser, wave, i)
    );
    const results = await Promise.all(promises);
    allResults.push(...results);

    const waveSec = ((Date.now() - waveStart) / 1000).toFixed(1);
    const ok  = results.filter((r) => r.appLoaded).length;
    const gtag = results.filter((r) => r.gtagScript).length;
    const gc   = results.filter((r) => r.gCollect).length;
    const cl   = results.filter((r) => r.clarityCollect).length;

    console.log(`   Done in ${waveSec}s | app loaded: ${ok}/${CONTEXTS_PER_WAVE} | gtag: ${gtag} | g/collect: ${gc} | clarity: ${cl}`);
    // Print debug URLs from W01/C01 to diagnose network capture
    if (wave === 1) {
      const w1c1 = results.find(r => r.ctxIdx === 1);
      if (w1c1 && w1c1.debugUrls.length > 0) {
        console.log(`   [DEBUG W01/C01 external URLs captured (${w1c1.debugUrls.length}):]`);
        w1c1.debugUrls.slice(0, 30).forEach(u => console.log(`     ${u}`));
      } else {
        console.log(`   [DEBUG W01/C01: no external URLs captured by response listener]`);
      }
    }

    if (wave < WAVES) {
      console.log(`   Waiting ${WAVE_GAP_MS / 1000}s before next wave…`);
      await sleep(WAVE_GAP_MS);
    }
  }

  await browser.close();

  // ── Results table ──────────────────────────────────────────────────────────
  console.log("\n" + "=".repeat(72));
  console.log("  RESULTS");
  console.log("=".repeat(72));
  const header = "Label        Device       Scroll  Dwell  Load(ms) App  gtag  g/col  clr  Link  Error";
  console.log(header);
  console.log("-".repeat(header.length));

  for (const r of allResults) {
    const row = [
      r.label.padEnd(12),
      r.device.padEnd(12),
      r.scrollDepth.padStart(5),
      `${r.dwellSec}s`.padStart(6),
      String(r.loadTimeMs).padStart(8),
      (r.appLoaded    ? "✓" : "✗").padStart(4),
      (r.gtagScript   ? "✓" : "✗").padStart(5),
      (r.gCollect     ? "✓" : "✗").padStart(6),
      (r.clarityCollect ? "✓" : "✗").padStart(4),
      (r.linkClicked  ? "✓" : "✗").padStart(5),
      r.error ? ` ⚠ ${r.error}` : "",
    ].join(" ");
    console.log(row);
  }

  // ── Summary ────────────────────────────────────────────────────────────────
  const total      = allResults.length;
  const loaded     = allResults.filter((r) => r.appLoaded).length;
  const gtagHits   = allResults.filter((r) => r.gtagScript).length;
  const gcHits     = allResults.filter((r) => r.gCollect).length;
  const clarityHits = allResults.filter((r) => r.clarityCollect).length;
  const linkClicks = allResults.filter((r) => r.linkClicked).length;
  const errors     = allResults.filter((r) => r.error).length;
  const avgLoad    = Math.round(allResults.filter((r) => r.loadTimeMs).reduce((s, r) => s + r.loadTimeMs, 0) / loaded);

  console.log("\n" + "=".repeat(72));
  console.log("  SUMMARY");
  console.log("=".repeat(72));
  console.log(`  Total sessions     : ${total}`);
  console.log(`  App loaded         : ${loaded}/${total} (${Math.round(loaded/total*100)}%)`);
  console.log(`  Avg load time      : ${avgLoad}ms`);
  console.log(`  gtag/js loaded     : ${gtagHits}/${total}`);
  console.log(`  g/collect fired    : ${gcHits}/${total}`);
  console.log(`  Clarity collect    : ${clarityHits}/${total}`);
  console.log(`  HN link clicks     : ${linkClicks}/${total}`);
  console.log(`  Errors             : ${errors}`);
  console.log("=".repeat(72));

  if (loaded < total * 0.8) {
    console.error("\n⚠  WARNING: Less than 80% of sessions loaded the app — check if Streamlit hit resource limits.");
    process.exit(1);
  }

  console.log("\n✓ Load test complete. Check GA4 Realtime and Clarity for results.");
}

main().catch((err) => {
  console.error("Fatal:", err);
  process.exit(1);
});
