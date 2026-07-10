import { test, expect, request, type Page } from "@playwright/test";
import { apiPost, loadSessions } from "../lib/api";

// F6 (Mock Committee) proven through the REAL deepagents graph: a fixture emits
// a real generate_committee_questions tool-call, which executes against the
// seeded project store (a crash would surface as an error bubble, failing the
// test), and the scripted follow-up renders the committee questions in chat.

async function sendTurn(page: Page, text: string) {
  await page.locator("textarea").first().fill(text);
  await page.getByRole("button", { name: "Send" }).click();
}

test("F6: the mock-committee tool runs in the real graph and renders questions", async ({ page }) => {
  const token = loadSessions().main.token;
  const rc = await request.newContext();
  // Seed enough thesis state that the defense tool has real weak points to mine.
  const seeded = await apiPost(rc, "/test/seed-project", {
    access_token: token,
    name: "E2E defense",
    slices: {
      M1: {
        research_title: "TikTok livestream shopping and Gen Z purchase intention",
        research_questions: ["RQ1: does streamer credibility affect purchase intention?"],
      },
      M3: { methodology: "PLS-SEM", conceptual_model: { nodes: [], edges: [] } },
      M4: { analysis_results: "AVE=0.62, HTMT ok, R2=0.41" },
    },
  });
  await rc.dispose();

  await page.goto(`/chat/projects/${seeded.project_id}/threads/${seeded.thread_id}`);
  await sendTurn(page, "prepare me for my defense");

  await expect(page.getByText(/questions your committee is most likely to ask/i).last())
    .toBeVisible({ timeout: 30_000 });
  // …and the [OPTIONS] marker renders as a clickable card grid (not raw text).
  await expect(page.getByTestId("card-grid-user_choice")).toBeVisible();
});
