import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./specs",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["json", { outputFile: "artifacts/report.json" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL,
    headless: true,
    screenshot: "only-on-failure",
    trace: "off",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  outputDir: "artifacts",
});
