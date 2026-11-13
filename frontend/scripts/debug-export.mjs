// Dev helper: reproduce the editor PNG export and print console output / toasts / download result.
import { chromium } from "@playwright/test";

const docId = process.argv[2];
const browser = await chromium.launch({ channel: "chrome", headless: true });
const ctx = await browser.newContext({ acceptDownloads: true, viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
page.on("console", (m) => console.log("console:", m.type(), m.text().slice(0, 300)));
page.on("pageerror", (e) => console.log("pageerror:", e.message));
page.on("download", (d) => console.log("DOWNLOAD:", d.suggestedFilename()));
await page.goto(`http://localhost:3000/editor/${docId}`, { waitUntil: "networkidle" });
await page.waitForTimeout(2500);
await page.getByRole("button", { name: "Export" }).click();
await page.getByRole("menuitem", { name: /PNG · native size/ }).click();
await page.waitForTimeout(4000);
const toasts = await page.locator("[data-sonner-toast]").allInnerTexts();
console.log("toasts:", JSON.stringify(toasts));
await browser.close();
