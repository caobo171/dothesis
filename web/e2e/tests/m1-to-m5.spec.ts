import { test, expect, request, type Page } from "@playwright/test";
import { createProjectWithThread, loadSessions } from "../lib/api";

test.describe.configure({ mode: "serial" });

let projectId: string;
let threadId: string;

test.beforeAll(async () => {
  const rc = await request.newContext();
  ({ projectId, threadId } = await createProjectWithThread(
    rc, loadSessions().main.token, "E2E M1-M5"));
  await rc.dispose();
});

async function sendTurn(page: Page, text: string) {
  await page.locator("textarea").first().fill(text);
  await page.getByRole("button", { name: "Send" }).click();
}

const turns = [
  { msg: "Let's finalize my topic: TikTok livestream shopping and Gen Z purchase intention.",
    module: "M1", reply: "M1 is committed" },
  { msg: "Now find the literature and gaps.", module: "M2", reply: "M2 is done" },
  { msg: "Design the study.", module: "M3", reply: "M3 is done" },
  { msg: "Analyze my survey data.", module: "M4", reply: "M4 is done" },
];

test("M1–M4 commits flip the ContextPanel modules to done", async ({ page }) => {
  await page.goto(`/chat/projects/${projectId}/threads/${threadId}`);
  for (const t of turns) {
    await sendTurn(page, t.msg);
    await expect(page.getByText(t.reply).last()).toBeVisible({ timeout: 30_000 });
    if (t.module === "M2") {
      // The scripted M2 confirmation embeds a {{cite: ...}} marker — the
      // chip's label must render (and the raw marker must not).
      await expect(page.getByText(/Nguyen & Tran/).first()).toBeVisible();
    }
    // moduleStatus reaches the panel via the project fetch; reload for a
    // deterministic read instead of racing the live refresh.
    await page.reload();
    await expect(page.getByTestId(`ctx-${t.module}`))
      .toHaveAttribute("data-status", "done", { timeout: 15_000 });
  }
});

test("M5 draft commit stores chapters and leaves earlier modules done", async ({ page }) => {
  await page.goto(`/chat/projects/${projectId}/threads/${threadId}`);
  await sendTurn(page, "Draft the chapters.");
  await expect(page.getByText("draft chapters are committed").last())
    .toBeVisible({ timeout: 30_000 });
  await page.reload();
  for (const m of ["M1", "M2", "M3", "M4"]) {
    await expect(page.getByTestId(`ctx-${m}`)).toHaveAttribute("data-status", "done");
  }
  // Deliberately in_progress, not done: flipping M5 to done fires
  // DbProjectStateStore's auto-export hook (soffice + S3 inside a status
  // journey). The export suite owns exporting, explicitly.
  await expect(page.getByTestId("ctx-M5")).toHaveAttribute("data-status", "in_progress");
});
