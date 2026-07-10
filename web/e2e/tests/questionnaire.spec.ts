import { test, expect, request, type Page } from "@playwright/test";
import { createProjectWithThread, loadSessions } from "../lib/api";

// F7 (Questionnaire Doctor) proven through the REAL deepagents graph: a fixture
// emits a real audit_instrument tool-call, which executes against the live tool
// (a crash would surface as an error bubble), and the scripted follow-up renders
// the audit findings in chat.

async function sendTurn(page: Page, text: string) {
  await page.locator("textarea").first().fill(text);
  await page.getByRole("button", { name: "Send" }).click();
}

test("F7: the questionnaire-doctor tool runs in the real graph and renders findings", async ({ page }) => {
  const rc = await request.newContext();
  const { projectId, threadId } = await createProjectWithThread(
    rc, loadSessions().main.token, "E2E questionnaire");
  await rc.dispose();

  await page.goto(`/chat/projects/${projectId}/threads/${threadId}`);
  await sendTurn(page, "check my questionnaire");

  await expect(page.getByText(/Questionnaire audit complete/i).last())
    .toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/double-barreled/i)).toBeVisible();
});
