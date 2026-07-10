import { test, expect, request } from "@playwright/test";
import { createProjectWithThread, loadSessions } from "../lib/api";

// @live tier: one REAL completion against the configured cheap model,
// verifying the marker convention survives an actual generation — the
// exact failure mode the Gemini 3.x content-shape regression had.
// Runs nightly/manual only (e2e.yml passes --grep @live and
// DOTHESIS_E2E_LIVE=1); self-skips in the mocked tier.
test("@live real model emits an [OPTIONS] marker that renders as a card grid", async ({ page }) => {
  test.skip(process.env.DOTHESIS_E2E_LIVE !== "1", "live tier only (nightly/manual)");

  const rc = await request.newContext();
  const { projectId, threadId } = await createProjectWithThread(
    rc, loadSessions().main.token, "E2E live smoke");
  await rc.dispose();

  await page.goto(`/chat/projects/${projectId}/threads/${threadId}`);
  await page.locator("textarea").first().fill(
    "Suggest exactly three possible quantitative research directions for a study " +
    "on e-wallet adoption among university students. End your reply with a single " +
    "[OPTIONS] line listing the three directions separated by | characters.",
  );
  await page.getByRole("button", { name: "Send" }).click();

  // Any card grid counts — the model chooses the field name.
  await expect(page.locator('[data-testid^="card-grid-"]').first())
    .toBeVisible({ timeout: 180_000 });
});
