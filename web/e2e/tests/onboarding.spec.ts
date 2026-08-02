import { test, expect } from "@playwright/test";

// First real fixture-driven journey. This is the integration proof point for
// the whole mock architecture: the FakeChatModel (Task 3) runs INSIDE a real
// deepagents graph here for the first time, replaying fixtures/onboarding.json.
// The journeys project starts logged-in via storageState (Task 4 auth setup).
test("drop-first onboarding: describe-it flow reaches chat with an options card", async ({ page }) => {
  await page.goto("/new");
  await expect(page.getByRole("heading", { name: "Analyze your thesis" })).toBeVisible();

  // Note-only (no upload) keeps PDF parsing out of this journey — upload
  // handling gets covered where it matters (export seeds via API). The composer
  // textarea is now the page's primary control, so there is no longer a
  // "Describe it instead" disclosure to open first.
  await page.getByLabel("Analyze your thesis").fill(
    "I am studying how TikTok livestream shopping affects Gen Z purchase intention in Hanoi. " +
    "I have survey data ready for SmartPLS but no literature review yet.",
  );
  await page.getByRole("button", { name: "Analyze", exact: true }).click();

  // /new creates a real project (+ Main thread) and lands in chat, where
  // ChatPane fires the real "/bootstrap" first turn automatically.
  await page.waitForURL(/\/chat\/projects\/[0-9a-f-]+/, { timeout: 45_000 });

  // The scripted analysis reply streams in…
  await expect(page.getByText("Detected topic")).toBeVisible({ timeout: 45_000 });
  // …its [OPTIONS] last line renders as a clickable card grid (unnamed marker →
  // field_name "user_choice" → data-testid card-grid-user_choice)…
  await expect(page.getByTestId("card-grid-user_choice")).toBeVisible();
  // …and the context store panel is on screen.
  await expect(page.getByTestId("context-panel")).toBeVisible();
});
