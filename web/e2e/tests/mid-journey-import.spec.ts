import { test, expect } from "@playwright/test";

// F12 (mid-journey import) proven in a real browser: dropping an existing
// analysis file on /new runs the server-side import (real upload → S3 →
// classify → commit) and lands on the ImportSummary activation card.
test("F12: dropping an analysis file lands on the activation summary card", async ({ page }) => {
  await page.goto("/new");
  await expect(page.getByRole("heading", { name: "Analyze your thesis" })).toBeVisible();

  // A .txt whose stat keywords make the importer classify it as analysis-output
  // via the deterministic _STAT_HINTS fast-path — no LLM needed — so M4 is
  // reconstructed deterministically and the test is stable under the mock tier.
  await page.locator('input[type="file"]').setInputFiles({
    name: "smartpls-results.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(
      "PLS-SEM results. AVE = 0.62. HTMT ok. Cronbach alpha 0.81. " +
      "Outer loadings all above 0.7. R square = 0.41. Path coefficient BI->ATT significant.",
    ),
  });
  await page.getByRole("button", { name: "Analyze", exact: true }).click();

  // /new swaps to the activation summary once the import returns.
  await expect(page.getByRole("heading", { name: "Here's where you are" }))
    .toBeVisible({ timeout: 60_000 });
  const summary = page.getByRole("region", { name: /import summary/i });
  await expect(summary).toBeVisible();
  // M4 (Analysis) was reconstructed from the upload; the CTA continues to chat.
  await expect(summary.getByText(/Imported:.*Analysis/)).toBeVisible();
  await expect(summary.getByRole("button", { name: /Continue to/ })).toBeVisible();
});
