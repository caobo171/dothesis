// web/e2e/tests/auth-billing.spec.ts
//
// The ONE suite that drives the REAL /login + /signup forms (no pre-authed
// storageState — the "auth-billing" Playwright project deliberately omits it,
// see playwright.config.ts), plus the credit-exhaustion journey against the
// verified 402 gate in api/app/routers/chat.py:send_message.
//
// DECISION: assertions target the REAL components/copy verified in source, not
// assumed strings:
//   - login bad-creds error → auth.py returns {error:{message:"invalid email
//     or password"}}; api.js ApiError.message surfaces it verbatim into the
//     login form's `text-destructive` div.
//   - out-of-credits banner + CTA → ChatPane.tsx renders "You're out of
//     credits." + a <Link href="/credit">Upgrade credits</Link> and disables
//     the composer when useMe() reports credit <= 0.
import path from "node:path";
import { test, expect, request } from "@playwright/test";
import { API_BASE, createProjectWithThread, loadSessions } from "../lib/api";

const BROKE_STATE = path.join(__dirname, "..", ".auth", "broke.json");

test("login rejects bad credentials with a visible error", async ({ page }) => {
  await page.goto("/login");
  // DECISION: example.com, not .test — LoginRequest.email is a pydantic
  // EmailStr, which 422s the reserved .test TLD BEFORE the bad_credentials
  // branch runs; a valid-but-unknown address reaches the real "invalid email
  // or password" 401 we're asserting on.
  await page.getByLabel("Email").fill("nobody@example.com");
  await page.getByLabel("Password").fill("definitely-wrong-1");
  await page.getByRole("button", { name: "Sign in" }).click();
  // The API's bad_credentials message rides ApiError.message verbatim.
  await expect(page.getByText("invalid email or password")).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
});

test("unauthenticated navigation is bounced to /login by the middleware", async ({ page }) => {
  // No cookie at all -> proxy.js redirects server-side (no content flash).
  await page.goto("/chat");
  await page.waitForURL(/\/login\?next=/);
});

test("a garbage token is wiped and redirected on the first API call", async ({ page, context }) => {
  // Cookie present (middleware lets the navigation through) but the token is
  // garbage -> the first authed fetch 401s -> app/lib/api.js clears the
  // store and hard-redirects to /login.
  await context.addCookies([{
    name: "dothesis_access_token", value: "garbage-token",
    domain: "localhost", path: "/",
  }]);
  await page.addInitScript(() => {
    localStorage.setItem("dothesis_access_token", "garbage-token");
    localStorage.setItem("dothesis_access_expires_at",
      String(Math.floor(Date.now() / 1000) + 3600));
  });
  await page.goto("/");
  await page.waitForURL(/\/login/, { timeout: 15_000 });
});

test("signup form creates an account and lands on wait-verify", async ({ page }) => {
  const stamp = Date.now();
  await page.goto("/signup");
  await page.getByLabel("Username").fill(`e2esignup${stamp}`);
  // DECISION: use example.com (not .test) — pydantic EmailStr rejects the
  // reserved .test TLD with a 422, same reason auth.setup.ts seeds example.com.
  await page.getByLabel("Email").fill(`e2e-signup-${stamp}@example.com`);
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Create account" }).click();
  // Real contract: signup returns {ok,email} (no token) and the client
  // routes to the check-your-email screen.
  await page.waitForURL(/\/wait-verify\?email=/);
});

test("credit-exhausted user: API 402s and the UI shows the upgrade CTA", async ({ browser }) => {
  const sessions = loadSessions();
  const rc = await request.newContext();
  const { projectId, threadId } = await createProjectWithThread(
    rc, sessions.broke.token, "E2E broke project");

  // API level: the turn is blocked up front with a structured 402 (verified
  // gate in chat.py send_message — blocks BEFORE persisting the message).
  const res = await rc.post(`${API_BASE}/threads/${threadId}/messages`, {
    data: { access_token: sessions.broke.token, text: "hello" },
  });
  expect(res.status()).toBe(402);
  expect((await res.json()).detail.error.code).toBe("insufficient_credit");
  await rc.dispose();

  // UI level: banner + CTA + disabled composer.
  const context = await browser.newContext({ storageState: BROKE_STATE });
  const page = await context.newPage();
  await page.goto(`/chat/projects/${projectId}/threads/${threadId}`);
  await expect(page.getByText("You're out of credits.")).toBeVisible();
  const cta = page.getByRole("link", { name: "Upgrade credits" });
  await expect(cta).toBeVisible();
  await expect(cta).toHaveAttribute("href", "/credit");
  await expect(page.locator("textarea").first()).toBeDisabled();
  await context.close();
});
