import { test, expect, type Page } from "@playwright/test";

const MOCK_EPISODES = [
  { id: 1, title: "What If the Internet Went Dark?", description: "A deep dive.", status: "built", output_object_key: "ep1/output.mp4", youtube_video_id: null, scenes: [{ id: 1 }, { id: 2 }] },
  { id: 2, title: "What If Mars Had Water?", description: "", status: "draft", output_object_key: null, youtube_video_id: null, scenes: [{ id: 3 }] },
];

async function setupAuth(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("access_token", "fake-jwt-token");
  });
}

test.describe("Dashboard — episode list", () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await page.route("**/api/episodes", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_EPISODES) })
    );
    await page.goto("/dashboard");
  });

  test("shows sidebar nav", async ({ page }) => {
    await expect(page.getByRole("link", { name: /episodes/i }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: /youtube/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /billing/i })).toBeVisible();
  });

  test("lists episodes from API", async ({ page }) => {
    await expect(page.getByText("What If the Internet Went Dark?")).toBeVisible();
    await expect(page.getByText("What If Mars Had Water?")).toBeVisible();
  });

  test("shows 'Built' badge for built episode", async ({ page }) => {
    await expect(page.getByText("Built")).toBeVisible();
  });

  test("shows 'Draft' badge for draft episode", async ({ page }) => {
    await expect(page.getByText("Draft")).toBeVisible();
  });

  test("episode links go to detail pages", async ({ page }) => {
    const link = page.getByRole("link", { name: /what if the internet/i }).first();
    await expect(link).toHaveAttribute("href", "/dashboard/episodes/1");
  });

  test("'New episode' button links to create form", async ({ page }) => {
    const btn = page.getByRole("link", { name: /new episode/i });
    await expect(btn).toHaveAttribute("href", "/dashboard/episodes/new");
  });
});

test.describe("Dashboard — empty state", () => {
  test("shows empty state when no episodes", async ({ page }) => {
    await setupAuth(page);
    await page.route("**/api/episodes", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) })
    );
    await page.goto("/dashboard");

    await expect(page.getByText("No episodes yet")).toBeVisible();
    await expect(page.getByRole("link", { name: /create episode/i })).toBeVisible();
  });
});

test.describe("Dashboard — unauthenticated", () => {
  test("redirects to /login when no token", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForURL("/login", { timeout: 10000 });
  });
});

test.describe("New episode form", () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await page.goto("/dashboard/episodes/new");
  });

  test("renders form fields", async ({ page }) => {
    await expect(page.getByPlaceholder(/what if the internet/i)).toBeVisible();
    await expect(page.getByText(/scenes \(1\)/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /add scene/i })).toBeVisible();
  });

  test("can add scenes dynamically", async ({ page }) => {
    await page.click('button:has-text("Add scene")');
    await expect(page.getByText(/scenes \(2\)/i)).toBeVisible();
    await page.click('button:has-text("Add scene")');
    await expect(page.getByText(/scenes \(3\)/i)).toBeVisible();
  });

  test("submits form and navigates to episode detail (mocked)", async ({ page }) => {
    await page.route("**/api/episodes", (route) => {
      if (route.request().method() === "POST") {
        route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ id: 99 }) });
      } else {
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ id: 99, title: "My Test Episode", status: "draft", scenes: [] }) });
      }
    });

    await page.fill('[placeholder="What If the Internet Went Dark?"]', "My Test Episode");
    await page.fill('[placeholder="Narration for scene 1…"]', "This is the narration for scene one.");
    await page.click('button[type="submit"]');

    await page.waitForURL("/dashboard/episodes/99", { timeout: 10000 });
  });
});
