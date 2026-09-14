import { expect, test } from "@playwright/test";

test("switches data modes and exposes their matching tools", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "NetTwin Security Panel" })).toBeVisible();
  await expect(page.getByText("Network Load Index", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "replay", exact: true }).click();
  await expect(page.getByRole("slider", { name: /Timeline/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Scenario Lab" })).toHaveCount(0);

  await page.getByRole("button", { name: "simulation", exact: true }).click();
  await expect(page.getByRole("button", { name: "Scenario Lab" })).toBeVisible();
});

test("creates a desktop measurement session", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Sessions" }).click();
  await expect(page.getByRole("heading", { name: "Measurement sessions" })).toBeVisible();

  const name = `Playwright session ${Date.now()}`;
  await page.getByLabel("Name").fill(name);
  await page.getByLabel("Notes").fill("Automated browser acceptance test");
  await page.getByRole("button", { name: "Create session" }).click();
  await expect(page.locator(".session-list strong", { hasText: name })).toBeVisible();
  await expect(page.getByRole("button", { name: "Capture now" }).last()).toBeVisible();
});
