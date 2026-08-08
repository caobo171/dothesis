import { test, expect, request } from "@playwright/test";
import { apiPost, loadSessions } from "../lib/api";

// F2 (coaching roadmap) + F4 (advisor loop) surfacing, proven in a real browser.
// Both seed a project through the test-support seam (no scripted agent turn) and
// assert the ContextPanel's RoadmapPanel — which fetches the real
// POST /projects/{id}/roadmap endpoint — renders the derived next action.

test("F2: roadmap panel surfaces the derived next action from real state", async ({ page }) => {
  const token = loadSessions().main.token;
  const rc = await request.newContext();
  // M1 has a title but no research questions → derive_substep(M1) = derive_questions.
  const seeded = await apiPost(rc, "/test/seed-project", {
    access_token: token,
    name: "E2E roadmap derived",
    slices: { M1: { research_title: "TikTok livestream & Gen Z purchase intention" } },
  });
  await rc.dispose();

  await page.goto(`/chat/projects/${seeded.project_id}/threads/${seeded.thread_id}`);
  const panel = page.getByTestId("roadmap-panel");
  await expect(panel).toBeVisible({ timeout: 20_000 });
  // The single derived Next action is "Derive research questions". exact:true
  // targets the Next-card title. It used to also have to avoid the panel's own
  // "▸ Derive research questions" sub-step line; that list now lives on the
  // module card instead of being printed a second time here.
  await expect(panel.getByText("Derive research questions", { exact: true })).toBeVisible();
});

test("F4: an open advisor directive surfaces as the Next blocker", async ({ page }) => {
  const token = loadSessions().main.token;
  const rc = await request.newContext();
  // M1 complete (so the derived step would otherwise advance), PLUS an open
  // advisor blocker — which must win next_action's precedence (blocker > advance).
  const seeded = await apiPost(rc, "/test/seed-project", {
    access_token: token,
    name: "E2E advisor loop",
    slices: { M1: { research_title: "T", research_questions: ["RQ1"] } },
    coaching: {
      advisor_feedback: [{
        id: "f1", chapter: "results", issue: "report effect sizes",
        required_change: "add Cohen's f2", status: "open",
      }],
      roadmap_tasks: [{
        id: "b1", module: "M4", substep: "interpret",
        title: "Advisor: report effect sizes", why: "add Cohen's f2",
        status: "open", feedback_id: "f1",
      }],
    },
  });
  await rc.dispose();

  await page.goto(`/chat/projects/${seeded.project_id}/threads/${seeded.thread_id}`);
  const panel = page.getByTestId("roadmap-panel");
  await expect(panel).toBeVisible({ timeout: 20_000 });
  // The advisor directive, raised as a blocker, is the leading next action.
  await expect(panel.getByText(/Advisor: report effect sizes/)).toBeVisible();
});

test("F11: the timeline you-are-here card shows progress-vs-plan", async ({ page }) => {
  const token = loadSessions().main.token;
  const rc = await request.newContext();
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  const shift = (days: number) => {
    const d = new Date();
    d.setDate(d.getDate() + days);
    return iso(d);
  };
  // Plan puts "today" inside the M2 (literature) window, but the project's focus
  // is still M1 (only M1 seeded) → timeline_status reports weeks-behind.
  const seeded = await apiPost(rc, "/test/seed-project", {
    access_token: token,
    name: "E2E timeline",
    slices: { M1: { research_title: "T" } },
    coaching: {
      thesis_timeline: {
        milestones: [
          { module: "M1", start: shift(-30), end: shift(-15), label: "Topic & questions", weeks: 2 },
          { module: "M2", start: shift(-14), end: shift(1), label: "Literature review", weeks: 2 },
        ],
      },
    },
  });
  await rc.dispose();

  await page.goto(`/chat/projects/${seeded.project_id}/threads/${seeded.thread_id}`);
  const card = page.getByTestId("timeline-card");
  await expect(card).toBeVisible({ timeout: 20_000 });
  await expect(card.getByText(/This week: Literature review/)).toBeVisible();
  await expect(card.getByText(/week\(s\) behind/)).toBeVisible();
});
