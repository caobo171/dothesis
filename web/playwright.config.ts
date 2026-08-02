import { defineConfig, devices } from "@playwright/test";
import path from "path";

// ---- E2E environment contract -------------------------------------------
// Ports are deliberately NOT the dev.sh ports (api 7100, web 3006, pg 5499):
// the harness must be able to run next to a live dev stack without touching it.
const API_PORT = 7143;
const WEB_PORT = 3106;
const API_URL = `http://localhost:${API_PORT}`;
const WEB_URL = `http://localhost:${WEB_PORT}`;

const apiDir = path.resolve(__dirname, "../api");
const fixturesDir = path.resolve(__dirname, "e2e/fixtures");
const workRoot = path.resolve(__dirname, "e2e/.work");
// Repo root of the checkout Playwright is launched from. This is deliberately
// put on the API's PYTHONPATH below: `pip install -e` registers the
// `dothesis_agent`/`dothesis_orchestrator` packages against ONE checkout's path
// (the main clone), so when the harness runs from a git worktree the uvicorn
// process would import a STALE `agent/` from the main clone — silently missing
// the fixture-mock hook (`DOTHESIS_E2E_MOCK` in agent/runtime._default_model)
// and any other worktree-only agent change. `app.*` already resolves correctly
// (it's found via the API's cwd on sys.path), but the sibling `agent`/
// `orchestrator` packages do not — hence pinning PYTHONPATH to THIS checkout so
// PathFinder wins over the editable-install finder. No-op when the worktree and
// the editable install happen to be the same path (a fresh CI clone).
const repoRoot = path.resolve(__dirname, "..");

// Playwright types webServer.env as Record<string, string>, but several values
// below come from process.env (typed string | undefined) and are meant to be
// omitted when unset — passing them through would either fail the build under
// strict TS or leak a literal "undefined" to the child process. pruneEnv drops
// undefined-valued keys and narrows the result to the required string map.
const pruneEnv = (
  env: Record<string, string | undefined>,
): Record<string, string> =>
  Object.fromEntries(
    Object.entries(env).filter((entry): entry is [string, string] => entry[1] !== undefined),
  );

// Live tier (nightly): real model, no fixture mock — but the test-support
// router stays on because the live smoke still needs seeded users.
const LIVE = process.env.DOTHESIS_E2E_LIVE === "1";

// DATABASE_URL comes from run-e2e.sh (ephemeral Docker Postgres). Fail early
// with a pointer instead of letting uvicorn die with a cryptic settings error.
if (!process.env.DATABASE_URL) {
  throw new Error(
    "DATABASE_URL is not set. Run the suite via web/e2e/run-e2e.sh — it boots " +
    "the ephemeral Postgres/MinIO containers and exports the env this config needs.",
  );
}

export default defineConfig({
  testDir: "./e2e/tests",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  // One worker: the suites share a single Postgres and a single mock-model
  // fixture registry; parallel workers would interleave scenario turns.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: WEB_URL,
    trace: "retain-on-failure",
    // Pinned because the UI language is now DETECTED from the browser timezone
    // (app/lib/i18n/locale.ts). Without this, Playwright inherits the host
    // clock, so the same suite renders English on a CI runner in UTC and
    // Vietnamese on a developer's machine in Asia/Ho_Chi_Minh — and every
    // assertion on English copy fails depending on who ran it. UTC is the
    // neutral choice: it maps to the default locale.
    timezoneId: "UTC",
  },
  projects: [
    // Runs first (project dependencies); Playwright starts webServers before
    // any project, so the API is up when this seeds users. NOTE: test
    // filters (--grep, file args) do NOT apply to dependency projects —
    // setup always runs in full, which the live tier's --grep relies on.
    { name: "setup", testMatch: /auth\.setup\.ts/ },
    // `/smoke\.spec\.ts/` used to also match live-smoke.spec.ts, which then ran
    // UNAUTHENTICATED here (no storageState) and false-failed in the live tier.
    // Anchor to a path separator so only smoke.spec.ts matches; live-smoke runs
    // in the authed `journeys` project.
    { name: "smoke", testMatch: /\/smoke\.spec\.ts/, use: { ...devices["Desktop Chrome"] } },
    {
      name: "journeys",
      testMatch: /(onboarding|m1-to-m5|export|roadmap|mid-journey-import|defense|questionnaire|live-smoke)\.spec\.ts/,
      dependencies: ["setup"],
      use: { ...devices["Desktop Chrome"], storageState: "e2e/.auth/user.json" },
    },
    {
      // The one suite that drives login/signup for real — no storageState.
      name: "auth-billing",
      testMatch: /auth-billing\.spec\.ts/,
      dependencies: ["setup"], // needs the seeded broke user
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      // The REAL api entrypoint (api/app/main.py: `app = create_app()`),
      // run through run.sh so the arm64 venv wrapper applies on macOS
      // (no-op passthrough on Linux/CI).
      command: `./run.sh uvicorn app.main:app --host 127.0.0.1 --port ${API_PORT}`,
      cwd: apiDir,
      url: `${API_URL}/api/v1/health`, // the repo's one GET endpoint
      reuseExistingServer: false,
      stdout: "pipe",
      stderr: "pipe",
      timeout: 120_000,
      env: pruneEnv({
        DATABASE_URL: process.env.DATABASE_URL,
        SESSION_SECRET: "dothesis-e2e-secret",
        // Force the sibling `agent`/`orchestrator` packages to load from THIS
        // checkout, not whatever clone `pip install -e` was originally run
        // against. Without this, a worktree run imports a stale main-clone
        // `agent/` that lacks the DOTHESIS_E2E_MOCK hook, so every fixture turn
        // builds a real model and 500s. See repoRoot note above.
        PYTHONPATH: repoRoot,
        // Chat/exports/uploads routers only mount when this is set
        // (api/app/main.py:create_app).
        ORCHESTRATOR_ENABLED: "true",
        // Test-support router (both tiers — live smoke still seeds users).
        DOTHESIS_TEST_SUPPORT: "1",
        // Mock model ONLY in the deterministic tier. Omit (not "") in live
        // mode so pydantic-settings never sees an empty-string bool.
        // In LIVE mode, forward the real model routing from the shell so the
        // live smoke exercises the ACTUAL configured deployment model (e.g.
        // Ofox -> qwen), not a hardcoded default. Only defined keys are set
        // (undefined ones are dropped by Playwright), so an env without these
        // still falls back to the app's own defaults.
        ...(LIVE ? {
          DOTHESIS_MODEL_ROUTE: process.env.DOTHESIS_MODEL_ROUTE,
          DOTHESIS_AGENT_MODEL: process.env.DOTHESIS_AGENT_MODEL,
          ORCHESTRATOR_LLM_ROUTE: process.env.ORCHESTRATOR_LLM_ROUTE,
          ORCHESTRATOR_LLM_MODEL: process.env.ORCHESTRATOR_LLM_MODEL,
          OFOX_API_KEY: process.env.OFOX_API_KEY,
          OPENROUTER_API_KEY: process.env.OPENROUTER_API_KEY,
          GOOGLE_API_KEY: process.env.GOOGLE_API_KEY,
          GEMINI_API_KEY: process.env.GEMINI_API_KEY,
        } : {
          DOTHESIS_E2E_MOCK: "1",
          DOTHESIS_E2E_FIXTURES_DIR: fixturesDir,
        }),
        // SES dummy mode (app/mail.py): signup logs the mail instead of
        // needing AWS creds.
        DOTHESIS_MAIL: "dummy",
        // CORS allowlist + verify/reset link host must match the browser origin.
        WEB_ORIGIN: WEB_URL,
        // Agent workspaces isolated from the dev tree.
        JOB_WORKDIR_ROOT: path.join(workRoot, "jobs"),
        // S3 → MinIO. The repo's boto3 factories read the custom
        // AWS_ACCESS_KEY/AWS_SECRET_KEY names; the standard names cover any
        // default-credential-chain fallback. AWS_ENDPOINT_URL_S3 is botocore's
        // native env endpoint override — no app changes needed.
        S3_BUCKET: "dothesis-e2e",
        AWS_ACCESS_KEY: "minioadmin",
        AWS_SECRET_KEY: "minioadmin",
        AWS_ACCESS_KEY_ID: "minioadmin",
        AWS_SECRET_ACCESS_KEY: "minioadmin",
        AWS_REGION: "us-east-1",
        AWS_ENDPOINT_URL_S3: process.env.AWS_ENDPOINT_URL_S3 ?? "http://localhost:9123",
      }),
    },
    {
      command: `npx next dev -p ${WEB_PORT}`,
      cwd: __dirname,
      url: `${WEB_URL}/login`,
      reuseExistingServer: false,
      stdout: "pipe",
      stderr: "pipe",
      timeout: 180_000,
      env: {
        // Relative fetch("/api/v1/…") goes through the next.config.mjs rewrite…
        NEXT_PUBLIC_API_PROXY_TARGET: API_URL,
        // …but several spots fetch the API directly and default to port 7100
        // (app/lib/api.js, uploads, export cards) — point them at 7143.
        NEXT_PUBLIC_API_BASE: `${API_URL}/api/v1`,
      },
    },
  ],
});
