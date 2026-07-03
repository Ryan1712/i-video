import { test, expect } from "@playwright/test";

test.describe("Landing page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("has correct title", async ({ page }) => {
    await expect(page).toHaveTitle(/What If\?/);
  });

  test("shows hero headline", async ({ page }) => {
    const h1 = page.locator("h1").first();
    await expect(h1).toContainText("Every");
    await expect(h1).toContainText("What If");
    await expect(h1).toContainText("Deserves to Be Seen");
  });

  test("nav has 'Get started free' CTA", async ({ page }) => {
    const cta = page.getByRole("link", { name: /get started free/i }).first();
    await expect(cta).toBeVisible();
    await expect(cta).toHaveAttribute("href", "/signup");
  });

  test("hero has primary CTA linking to signup", async ({ page }) => {
    const cta = page.getByRole("link", { name: /start your first episode/i });
    await expect(cta).toBeVisible();
    await expect(cta).toHaveAttribute("href", "/signup");
  });

  test("features section is present", async ({ page }) => {
    await expect(page.getByText("AI Scene Writing")).toBeVisible();
    await expect(page.getByText("Cinematic Rendering")).toBeVisible();
    await expect(page.getByText("YouTube Publishing")).toBeVisible();
  });

  test("pricing section shows all three plans", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Free", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Creator", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Studio", exact: true })).toBeVisible();
  });

  test("footer has brand name", async ({ page }) => {
    await expect(page.getByText(/© 2026 What If\?/)).toBeVisible();
  });

  test("nav links scroll to sections", async ({ page }) => {
    const featuresLink = page.getByRole("link", { name: "Features" }).first();
    await expect(featuresLink).toHaveAttribute("href", "#features");
  });
});
