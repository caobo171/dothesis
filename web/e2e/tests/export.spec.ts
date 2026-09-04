import { test, expect, request, type Page } from "@playwright/test";
import { apiPost, loadSessions } from "../lib/api";

// run_export builds the PDF with LibreOffice headless (soffice) —
// unconditionally, so the whole journey needs it. run-e2e.sh sets the flag
// when soffice is on PATH; CI installs libreoffice-writer.
test.skip(!process.env.DOTHESIS_E2E_HAS_SOFFICE,
  "export needs LibreOffice (soffice) for the PDF leg — install it or run in CI");

let projectId: string;
let threadId: string;

// FIVE chapters, not six: the discussion of findings is written INSIDE the
// closing chapter rather than as a chapter of its own, matching the backend's
// collapsed M5_CHAPTER_ORDER / M5_CHAPTER_TITLES (orchestrator/tools/
// m5_writing.py). The title below must match that map's `conclusion` entry
// exactly, or chapters_from_final_sections' title reverse-lookup drops the
// section instead of mapping it.
const FIVE_CHAPTERS = [
  ["Chapter 1 — Introduction", "This study examines how TikTok livestream shopping shapes Gen Z purchase intention in Hanoi. It motivates the research problem, presents the research questions, and outlines the thesis structure."],
  ["Chapter 2 — Literature Review", "Prior research links streamer credibility and livestream engagement to consumer purchase behavior. This chapter reviews that work and positions the perceived-scarcity gap this study addresses."],
  ["Chapter 3 — Methodology", "A quantitative cross-sectional survey design was used. Data from 350 Gen Z respondents in Hanoi were analyzed with PLS-SEM in SmartPLS 4, following a two-step measurement and structural model assessment."],
  ["Chapter 4 — Results", "The measurement model showed adequate reliability and validity (CR 0.84-0.91; AVE 0.58-0.67; HTMT below 0.85). H1 was supported (beta = 0.41, p < 0.001) and H2 was supported (indirect beta = 0.18, p < 0.01), with R2 of 0.52 for purchase intention."],
  ["Chapter 5 — Conclusions and Recommendations", "The findings confirm that streamer credibility is the dominant driver of purchase intention, while perceived scarcity partially transmits the effect of engagement. Theoretical and managerial implications are discussed. The study answers both research questions and contributes a scarcity-mediation account of livestream commerce among Vietnamese Gen Z. Limitations and directions for future research close the thesis."],
].map(([title, prose]) => ({ title, prose }));

test.beforeAll(async () => {
  const rc = await request.newContext();
  const token = loadSessions().main.token;
  // Seed through the guarded store: M1–M4 done, M5 holds a COMPLETE
  // five-chapter draft but stays in_progress (a done-flip would fire the
  // auto-export hook during seeding — this journey must trigger export
  // itself, through the chat turn).
  const seeded = await apiPost(rc, "/test/seed-project", {
    access_token: token,
    name: "E2E export thesis",
    slices: {
      M1: {
        research_title: "The impact of TikTok livestream shopping on Gen Z purchase intention in Hanoi",
        research_questions: ["RQ1: How does streamer credibility affect purchase intention?"],
      },
      M2: {
        literature_sources: [{
          title: "Live streaming commerce and consumer purchase intention",
          authors: "Nguyen, T. & Tran, H.", year: 2024,
          venue: "Journal of Retailing and Consumer Services",
          doi: "10.1016/j.jretconser.2024.0001",
        }],
      },
      M3: { methodology: "Quantitative survey; PLS-SEM in SmartPLS 4; n=350." },
      M4: { analysis_results: "CR 0.84-0.91; AVE 0.58-0.67; HTMT < 0.85; H1 beta=0.41 p<0.001; R2=0.52." },
      M5: { final_sections: FIVE_CHAPTERS },
    },
    done: ["M1", "M2", "M3", "M4"],
  });
  projectId = seeded.project_id;
  threadId = seeded.thread_id;
  await rc.dispose();
});

async function sendTurn(page: Page, text: string) {
  await page.locator("textarea").first().fill(text);
  await page.getByRole("button", { name: "Send" }).click();
}

test("export turn produces a real, downloadable DOCX (and a PDF button)", async ({ page }) => {
  await page.goto(`/chat/projects/${projectId}/threads/${threadId}`);
  await sendTurn(page, "Export my thesis");

  // Real engine work happens here: DOCX build + LibreOffice PDF + MinIO
  // upload — generous timeout, this is the slowest journey by design.
  const card = page.getByTestId("export-artifacts-card");
  await expect(card).toBeVisible({ timeout: 120_000 });

  const docx = card.getByRole("link", { name: "DOCX" });
  await expect(docx).toBeVisible();
  await expect(card.getByRole("link", { name: "PDF" })).toBeVisible();

  // Click follows the REAL path: mint stream token -> GET
  // /projects/{id}/exports/{file}?st= -> 302 -> MinIO presigned URL.
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    docx.click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/\.docx$/i);
});
