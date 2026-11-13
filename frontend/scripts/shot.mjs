// Dev helper: screenshot app routes at desktop + tablet sizes using the installed Chrome.
// Usage: node scripts/shot.mjs <outDir> /route1 /route2 ...   (set WIDTHS=1440,834 to override)
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const [, , outDir, ...routes] = process.argv;
const widths = (process.env.WIDTHS ?? "1440,834").split(",").map(Number);
const base = process.env.BASE ?? "http://localhost:3000";
fs.mkdirSync(outDir, { recursive: true });
const browser = await chromium.launch({ channel: "chrome", headless: true });
const errors = [];
for (const w of widths) {
  const page = await browser.newPage({ viewport: { width: w, height: w > 1000 ? 900 : 1112 } });
  page.on("pageerror", (e) => errors.push(`${w} ${page.url()}: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") errors.push(`${w} ${page.url()} console: ${m.text().slice(0, 300)}`); });
  for (const r of routes) {
    await page.goto(base + r, { waitUntil: "networkidle", timeout: 90000 }).catch((e) => errors.push(`${r}: ${e.message}`));
    await page.waitForTimeout(Number(process.env.WAIT ?? 800));
    const name = `${(r.replace(/[^a-z0-9]+/gi, "_").replace(/^_|_$/g, "") || "home")}_${w}.png`;
    await page.screenshot({ path: path.join(outDir, name), fullPage: process.env.FULL === "1" });
    console.log("shot", name);
  }
  await page.close();
}
await browser.close();
if (errors.length) console.log("ERRORS:\n" + errors.join("\n"));
