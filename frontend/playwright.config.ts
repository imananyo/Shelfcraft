import { defineConfig } from "@playwright/test";

// E2E tests run against an already running Shelfcraft (scripts\start.ps1) using installed Chrome.
export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["json", { outputFile: "test-results/e2e-results.json" }]],
  use: { baseURL: process.env.BASE ?? "http://localhost:3000", channel: "chrome", headless: true, viewport: { width: 1440, height: 900 }, trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 900 } } },
    { name: "tablet", use: { viewport: { width: 834, height: 1112 } }, testMatch: /navigation\.spec\.ts/ },
  ],
});
