import { defineConfig } from "@playwright/test";

// E2E tests create brands, products and projects, and switch the active brand. They must run against the isolated
// test instance (scripts\test-instance.ps1 → http://127.0.0.1:3100, its own empty database), never your real
// workspace on :3000. Running them against :3000 once filled the real database with "E2E Brand …" brands.
const BASE = process.env.BASE ?? "http://127.0.0.1:3100";
if (/:(3000)(\/|$)/.test(BASE) && process.env.ALLOW_REAL_WORKSPACE !== "1") {
  throw new Error(
    `Refusing to run E2E tests against ${BASE}: that is your real Shelfcraft workspace and the tests would add test data to it. ` +
    "Start the isolated test instance (scripts\\test-instance.ps1) and use BASE=http://127.0.0.1:3100, " +
    "or set ALLOW_REAL_WORKSPACE=1 if you really mean it.");
}

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["json", { outputFile: "test-results/e2e-results.json" }]],
  use: { baseURL: BASE, channel: "chrome", headless: true, viewport: { width: 1440, height: 900 }, trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 900 } } },
    { name: "tablet", use: { viewport: { width: 834, height: 1112 } }, testMatch: /navigation\.spec\.ts/ },
  ],
});
