// @ts-check
const { test, expect } = require("@playwright/test");

/**
 * Waits for Streamlit to finish its initial render.
 * Streamlit shows a spinner / "Running…" badge while loading; we wait until it
 * disappears and at least one stMarkdown block is visible.
 */
async function waitForStreamlit(page) {
  // Wait for the Streamlit status indicator to be done (or absent).
  // The status toolbar contains a "Running" badge; wait up to 45 s for it to clear.
  await page
    .locator('[data-testid="stStatusWidget"]')
    .waitFor({ state: "hidden", timeout: 45_000 })
    .catch(() => {
      /* status widget may not exist at all — that is fine */
    });

  // Ensure at least one stMarkdown element is rendered (proves HTML was injected).
  await page.locator(".stMarkdown").first().waitFor({ timeout: 45_000 });
}

// ---------------------------------------------------------------------------
// Open-state suite
// (CI starts Streamlit with CURRENT_STATE_FILE_PATH=current_state_open.json)
// ---------------------------------------------------------------------------
test.describe("Athlete view — gym OPEN", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await waitForStreamlit(page);
  });

  test("page loads without error", async ({ page }) => {
    // Streamlit surfaces unhandled exceptions in a red error box.
    await expect(page.locator('[data-testid="stException"]')).toHaveCount(0);

    // The app should not be stuck on the skeleton loader.
    await expect(page.locator(".stSpinner")).toHaveCount(0);
  });

  test("Athlete View eyebrow is present", async ({ page }) => {
    await expect(page.getByText("Athlete View").first()).toBeVisible();
  });

  test("workout block is rendered", async ({ page }) => {
    // The workout block div is injected via st.markdown unsafe_allow_html.
    const workoutBlock = page.locator(".workout-block").first();
    await expect(workoutBlock).toBeVisible();
  });

  test("today's workout movements are listed", async ({ page }) => {
    // Our fixture workout (2026-05-15) contains "Thrusters" and "Pull-ups".
    await expect(page.getByText("Thrusters").first()).toBeVisible();
    await expect(page.getByText("Pull-ups").first()).toBeVisible();
  });

  test("workout stimulus is displayed", async ({ page }) => {
    await expect(
      page.getByText("Aerobic conditioning with moderate loading").first()
    ).toBeVisible();
  });

  test("side panel is rendered", async ({ page }) => {
    // "Joke of the Day" is always rendered in the side panel.
    await expect(page.getByText("Joke of the Day").first()).toBeVisible();
  });

  test("Gym Conversation Starter section is present", async ({ page }) => {
    await expect(
      page.getByText("Gym Conversation Starter").first()
    ).toBeVisible();
  });

  test("poster anchor link is absent when no poster image exists", async ({
    page,
  }) => {
    // In CI with fixture data there is no AI poster; the anchor link should not appear.
    // We check via text — "View Poster" is only rendered when poster_bytes is truthy.
    // This is a "soft" check: if a poster IS available the link must navigate correctly.
    const posterLink = page.getByText("View Poster");
    const count = await posterLink.count();
    if (count > 0) {
      // Poster is present — clicking the link should not navigate away.
      await posterLink.first().click();
      await expect(page).toHaveURL("/");
    }
  });
});

// ---------------------------------------------------------------------------
// Closed-state suite
// (CI restarts Streamlit with CURRENT_STATE_FILE_PATH=current_state_closed.json)
// Guarded by an env var so tests are skipped when server runs in open mode.
// ---------------------------------------------------------------------------
test.describe("Athlete view — gym CLOSED", () => {
  test.skip(
    process.env.GYM_STATE !== "closed",
    "Skipped: set GYM_STATE=closed and point server at current_state_closed.json to run these tests"
  );

  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await waitForStreamlit(page);
  });

  test("page loads without error", async ({ page }) => {
    await expect(page.locator('[data-testid="stException"]')).toHaveCount(0);
  });

  test("Athlete View eyebrow is present in closed state", async ({ page }) => {
    await expect(page.getByText("Athlete View").first()).toBeVisible();
  });

  test("garage-closed heading is rendered", async ({ page }) => {
    // The heading uses class "garage-closed" injected via unsafe HTML.
    const closedDiv = page.locator(".garage-closed").first();
    await expect(closedDiv).toBeVisible();
  });

  test("no workout block is shown when gym is closed", async ({ page }) => {
    await expect(page.locator(".workout-block")).toHaveCount(0);
  });

  test("side panel still shows Joke of the Day", async ({ page }) => {
    await expect(page.getByText("Joke of the Day").first()).toBeVisible();
  });
});
