import { test, expect } from "@playwright/test";

// Cheapest full-stack signal. If the harness breaks, run this first: it
// isolates "environment won't boot" from "a journey regressed".
test("stack boots: API health responds and the login page renders", async ({ page, request }) => {
  const health = await request.get("http://localhost:7143/api/v1/health");
  expect(await health.json()).toEqual({ ok: true });

  await page.goto("/login");
  await expect(page.getByLabel("Email")).toBeVisible();
  await expect(page.getByLabel("Password")).toBeVisible();
});
