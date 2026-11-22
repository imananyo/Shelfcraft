import { expect, test } from "@playwright/test";
import zlib from "node:zlib";

/** Minimal valid PNG (solid color) generated in-test — no external assets. */
function png(w: number, h: number, rgb: [number, number, number]): Buffer {
  const crc = (buf: Buffer) => { let c = ~0; for (const b of buf) { c ^= b; for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xedb88320 & -(c & 1)); } return ~c >>> 0; };
  const chunk = (type: string, data: Buffer) => { const len = Buffer.alloc(4); len.writeUInt32BE(data.length); const td = Buffer.concat([Buffer.from(type), data]); const c = Buffer.alloc(4); c.writeUInt32BE(crc(td)); return Buffer.concat([len, td, c]); };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 2;
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array.from({ length: w }, () => rgb).flat())]);
  const raw = Buffer.concat(Array.from({ length: h }, () => row));
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", ihdr), chunk("IDAT", zlib.deflateSync(raw)), chunk("IEND", Buffer.alloc(0))]);
}
const stamp = Date.now().toString(36);

test("create and edit a brand", async ({ page }) => {
  await page.goto("/brands/new");
  await page.getByPlaceholder("e.g. Northwind Goods").fill(`E2E Brand ${stamp}`);
  await page.getByPlaceholder("e.g. Bold, confident, approachable").fill("Friendly");
  await page.getByRole("button", { name: "Create brand" }).click();
  await expect(page).toHaveURL(/\/brands\/[a-f0-9]{32}/);
  await page.getByPlaceholder("e.g. Performance meets design").fill("Tested end to end");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Brand saved")).toBeVisible();
  await page.reload();
  await expect(page.getByPlaceholder("e.g. Performance meets design")).toHaveValue("Tested end to end");
});

test("add a product with a photo, edit details, persist", async ({ page }) => {
  await page.goto("/products");
  await page.getByRole("button", { name: "Add product" }).first().click();
  await page.getByRole("button", { name: "Enter details manually" }).click();
  await page.locator('input[type=file]').first().setInputFiles({ name: "p.png", mimeType: "image/png", buffer: png(64, 64, [42, 157, 143]) });
  await page.getByPlaceholder("e.g. Insulated Steel Bottle 750 ml").fill(`E2E Product ${stamp}`);
  await page.getByRole("dialog").getByRole("button", { name: "Add product", exact: true }).click();
  await expect(page).toHaveURL(/\/products\/[a-f0-9]{32}/);
  await page.getByRole("tab", { name: /Images/ }).click();
  await expect(page.getByText("Main", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Details" }).click();
  await page.locator("textarea").first().fill("Made for testing.");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Product saved")).toBeVisible();
  await page.reload();
  await expect(page.locator("textarea").first()).toHaveValue("Made for testing.");
});

test("editor: add layers, undo/redo, autosave survives reload, export PNG", async ({ page }) => {
  test.setTimeout(240_000); // includes first-visit dev compile of the editor bundle
  await page.goto("/projects?new=1");
  await page.getByRole("dialog").getByRole("button", { name: /Square post/ }).click();
  await page.getByRole("button", { name: "Create design" }).click();
  await expect(page).toHaveURL(/\/editor\//);
  await page.getByRole("button", { name: "Text (T)" }).click();
  await page.getByRole("button", { name: "Rectangle (R)" }).click();
  await expect(page.getByText("Your text")).toBeVisible();
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.locator("aside").getByText("Rectangle")).toHaveCount(0);
  await page.getByRole("button", { name: "Redo" }).click();
  await expect(page.locator("aside").getByText("Rectangle")).toBeVisible();
  await expect(page.getByText(/^Saved/)).toBeVisible({ timeout: 15000 });
  await page.reload();
  await expect(page.locator("aside").getByText("Rectangle")).toBeVisible();
  await expect(page.locator("aside").getByText("Your text")).toBeVisible();
  await page.getByRole("button", { name: "Export" }).click();
  const item = page.getByRole("menuitem", { name: /PNG · native size/ });
  await item.waitFor({ state: "visible" });
  await page.waitForTimeout(300); // let the menu finish opening before selecting
  const [dl] = await Promise.all([page.waitForEvent("download", { timeout: 30_000 }), item.click()]);
  expect(dl.suggestedFilename()).toMatch(/\.png$/);
});

test("asset library: upload, favorite, filter", async ({ page }) => {
  await page.goto("/library");
  await page.locator("#lib-upload").setInputFiles({ name: `lib-${stamp}.png`, mimeType: "image/png", buffer: png(48, 48, [231, 111, 81]) });
  await expect(page.getByText(/Uploaded 1 file/)).toBeVisible();
  await page.getByRole("button", { name: `Open lib-${stamp}.png` }).click();
  await page.getByRole("button", { name: /^Favorite$/ }).click();
  await expect(page.getByRole("button", { name: /Favorited/ })).toBeVisible();
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await page.getByRole("button", { name: "Favorites only" }).click();
  await expect(page.getByRole("button", { name: `Open lib-${stamp}.png` })).toBeVisible();
});

test("settings: paid/unverified provider cannot be enabled; keys never rendered", async ({ page }) => {
  await page.goto("/settings");
  const mistral = page.locator("div").filter({ hasText: /^Mistral \(unverified/ }).first();
  await expect(page.getByText("Not free — blocked")).toBeVisible();
  await expect(mistral.getByRole("switch")).toBeDisabled();
  const html = await page.content();
  expect(html).not.toMatch(/gsk_[A-Za-z0-9]{10,}|AIza[0-9A-Za-z_-]{20,}|sk-or-[A-Za-z0-9-]{10,}/);
});

test("new listing: add a product inline and it is auto-selected", async ({ page }) => {
  await page.goto("/listings/new");
  await page.getByRole("button", { name: "New product" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.locator("input[type=file]").setInputFiles({ name: "q.png", mimeType: "image/png", buffer: png(64, 64, [200, 120, 60]) });
  await dialog.getByPlaceholder("e.g. Bamboo Cutting Board, Large").fill(`Inline Product ${stamp}`);
  await dialog.getByPlaceholder("e.g. Organic bamboo, juice groove").fill("Organic bamboo");
  await dialog.getByRole("button", { name: "Add & select" }).click();
  await expect(dialog).toBeHidden();
  const select = page.getByRole("combobox", { name: "Product" });
  await expect(select.locator("option:checked")).toHaveText(`Inline Product ${stamp}`);
});
test("listing grader: paste a listing and get a score with fixes", async ({ page }) => {
  await page.goto("/grader");
  // The grader opens on "From an Amazon URL"; this journey uses the paste form.
  await expect(page.getByRole("textbox", { name: "Amazon product link or ASIN" })).toBeVisible();
  await page.getByRole("tab", { name: "Paste a listing" }).click();
  await page.locator("textarea").first().fill("BEST SALE water bottle");
  await page.getByRole("button", { name: "Grade listing" }).click();
  await expect(page.getByText(/^Grade [A-F]$/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Top fixes" })).toBeVisible();
});

test("playbooks: import a template and see its steps", async ({ page }) => {
  await page.goto("/playbooks");
  await page.getByRole("button", { name: "Playbook templates" }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.locator("div").filter({ hasText: /^Lifestyle trio/ }).first().waitFor();
  await dialog.getByRole("button", { name: "Import" }).nth(1).click();
  await expect(page).toHaveURL(/\/playbooks\/[a-f0-9]{32}/);
  await expect(page.getByRole("heading", { name: /Steps \(\d+\)/ })).toBeVisible();
});

test("playbooks: edit steps, unsaved badge, save, duplicate", async ({ page }) => {
  await page.goto("/playbooks");
  await page.getByRole("button", { name: "New playbook" }).first().click();
  await expect(page).toHaveURL(/\/playbooks\/[a-f0-9]{32}/);
  await expect(page.getByRole("button", { name: "Saved", exact: true })).toBeDisabled();
  await page.getByRole("textbox", { name: "Playbook name" }).fill("E2E copy kit");
  await expect(page.getByText("Unsaved changes")).toBeVisible();
  // switching a step's kind gives a clean step of that kind (no stale image type)
  await page.getByRole("combobox", { name: "Step 1 kind" }).selectOption("listing_copy");
  await page.getByRole("combobox", { name: "Language" }).selectOption("de");
  await page.getByRole("button", { name: "Video", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Steps (2)" })).toBeVisible();
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("button", { name: "Saved", exact: true })).toBeVisible();
  await expect(page.getByText("Listing copy · DE")).toBeVisible();
  await page.getByRole("button", { name: "Duplicate playbook" }).click();
  await expect(page.getByRole("heading", { name: /E2E copy kit \(copy\)/ })).toBeVisible();
});

test("api keys: create a key, call the public API, revoke it", async ({ page, request }) => {
  await page.goto("/settings?tab=api");
  await page.getByRole("button", { name: "Create key" }).click();
  const key = (await page.locator("code").filter({ hasText: /^sk_shelf_/ }).first().textContent())!.trim();
  const ok = await request.get("/v1/products", { headers: { Authorization: `Bearer ${key}` } });
  expect(ok.status()).toBe(200);
  expect((await request.get("/v1/products")).status()).toBe(401);
});