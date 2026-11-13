// Dev helper: check whether editor web fonts load (Google Fonts link + FontFaceSet status).
import { chromium } from "@playwright/test";

const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage();
page.on("requestfailed", (r) => console.log("FAILED:", r.url().slice(0, 120), r.failure()?.errorText));
page.on("response", (r) => { if (r.url().includes("fonts.g")) console.log("font response:", r.status(), r.url().slice(0, 110)); });
await page.goto(`http://localhost:3000/editor/${process.argv[2]}`, { waitUntil: "networkidle" });
await page.waitForTimeout(5000);
console.log(await page.evaluate(() => ({
  links: [...document.querySelectorAll('link[id^="gf-"]')].map((l) => l.getAttribute("href")),
  fraunces700: document.fonts.check('700 24px "Fraunces"'),
  manrope400: document.fonts.check('400 24px "Manrope"'),
  faces: [...document.fonts].filter((f) => /Fraunces|Manrope/.test(f.family)).map((f) => `${f.family} ${f.weight} ${f.status}`).slice(0, 8),
})));
await browser.close();
