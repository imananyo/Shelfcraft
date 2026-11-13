import { expect, test } from "@playwright/test";

const ROUTES: [string, RegExp][] = [
  ["/create", /What should we work on/], ["/listings", /Listing builder/],
  ["/studio", /Image studio/], ["/edit", /Spot edit/], ["/aplus", /A\+ content/], ["/videos", /Video creator/],
  ["/inspire", /Inspire/], ["/factory", /Factory/], ["/projects", /Designs & projects/], ["/library", /Asset library/],
  ["/jobs", /Jobs/], ["/brands", /Brands/], ["/products", /Products/], ["/settings", /Settings/],
];

test("every main page renders without runtime errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(`${page.url()}: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error" && !m.text().includes("fonts.googleapis")) errors.push(`${page.url()}: ${m.text()}`); });
  await page.goto("/");
  await expect(page.getByText(/^(Working on|Welcome)$/i)).toBeVisible(); // dashboard h1 is the active brand name
  for (const [path, heading] of ROUTES) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 }).first()).toHaveText(heading);
  }
  expect(errors).toEqual([]);
});

test("sidebar links all resolve (no dead navigation)", async ({ page, request }) => {
  await page.goto("/");
  await page.locator('nav[aria-label="Main"] a').first().waitFor({ state: "attached" });
  const hrefs = await page.locator('nav[aria-label="Main"] a').evaluateAll((as) => as.map((a) => a.getAttribute("href")));
  expect(hrefs.length).toBeGreaterThan(10);
  for (const h of hrefs) {
    const r = await request.get(h!);
    expect(r.status(), h!).toBe(200);
  }
});

test("search palette opens with Ctrl+K and navigates", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Control+k");
  await page.getByPlaceholder(/Search products/).fill("Settings");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/settings/);
});
