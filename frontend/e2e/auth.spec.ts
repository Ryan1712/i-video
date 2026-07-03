import { test, expect } from "@playwright/test";

test.describe("Login page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/login");
  });

  test("renders login form", async ({ page }) => {
    await expect(page.getByText("Welcome back")).toBeVisible();
    await expect(page.getByPlaceholder("you@example.com")).toBeVisible();
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
  });

  test("has link to signup page", async ({ page }) => {
    const link = page.getByRole("link", { name: /sign up free/i });
    await expect(link).toHaveAttribute("href", "/signup");
  });

  test("shows error on invalid credentials (mocked)", async ({ page }) => {
    await page.route("**/api/auth/login", (route) =>
      route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Invalid credentials" }) })
    );

    await page.fill('[placeholder="you@example.com"]', "wrong@example.com");
    await page.fill('[placeholder="••••••••"]', "wrongpass");
    await page.click('button[type="submit"]');

    await expect(page.getByText("Invalid email or password.")).toBeVisible();
  });

  test("redirects to dashboard on successful login (mocked)", async ({ page }) => {
    await page.route("**/api/auth/login", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ access_token: "fake-jwt-token", token_type: "bearer" }),
      })
    );
    await page.route("**/api/episodes", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) })
    );

    await page.fill('[placeholder="you@example.com"]', "test@example.com");
    await page.fill('[placeholder="••••••••"]', "password123");
    await page.click('button[type="submit"]');

    await page.waitForURL("/dashboard", { timeout: 10000 });
  });
});

test.describe("Signup page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/signup");
  });

  test("renders signup form", async ({ page }) => {
    await expect(page.getByText("Create your account")).toBeVisible();
    await expect(page.getByPlaceholder("Min. 8 characters")).toBeVisible();
    await expect(page.getByRole("button", { name: /create account/i })).toBeVisible();
  });

  test("has link to login page", async ({ page }) => {
    const link = page.getByRole("link", { name: /sign in/i });
    await expect(link).toHaveAttribute("href", "/login");
  });

  test("shows error when passwords do not match", async ({ page }) => {
    await page.fill('[placeholder="you@example.com"]', "new@example.com");
    await page.fill('[placeholder="Min. 8 characters"]', "password123");
    await page.fill('[placeholder="••••••••"]', "different456");
    await page.click('button[type="submit"]');

    await expect(page.getByText("Passwords do not match.")).toBeVisible();
  });

  test("shows error when password is too short", async ({ page }) => {
    await page.fill('[placeholder="you@example.com"]', "new@example.com");
    await page.fill('[placeholder="Min. 8 characters"]', "short");
    await page.fill('[placeholder="••••••••"]', "short");
    await page.click('button[type="submit"]');

    await expect(page.getByText("Password must be at least 8 characters.")).toBeVisible();
  });

  test("creates account and redirects to dashboard (mocked)", async ({ page }) => {
    await page.route("**/api/auth/signup", (route) =>
      route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ id: 1, email: "new@example.com" }) })
    );
    await page.route("**/api/auth/login", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ access_token: "fake-jwt-token", token_type: "bearer" }),
      })
    );
    await page.route("**/api/episodes", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) })
    );

    await page.fill('[placeholder="you@example.com"]', "new@example.com");
    await page.fill('[placeholder="Min. 8 characters"]', "password123");
    await page.fill('[placeholder="••••••••"]', "password123");
    await page.click('button[type="submit"]');

    await page.waitForURL("/dashboard", { timeout: 10000 });
  });
});
