// web/e2e/tests/auth.setup.ts
import fs from "node:fs";
import path from "node:path";
import { test as setup } from "@playwright/test";
import { AUTH_DIR, WEB_ORIGIN, apiPost, type Session } from "../lib/api";

// Auth is body-token (no auth cookies): login returns {access_token,
// expires_at}; the client keeps it in TWO places (tokenStore.ts) —
// localStorage (canonical, read by every fetch) and a non-HTTPOnly cookie
// mirror of the SAME name that web/proxy.js checks to gate navigation.
// storageState must contain both or the first page load bounces to /login.
// (proxy.js only checks the cookie's PRESENCE, not its value, so the raw
// token here is fine even though the app URL-encodes it when it sets the
// cookie itself.)
function writeStorageState(name: string, token: string, expiresAt: number) {
  const state = {
    cookies: [{
      name: "dothesis_access_token",
      value: token,
      domain: "localhost",
      path: "/",
      expires: Math.floor(Date.now() / 1000) + 6 * 24 * 3600,
      httpOnly: false,
      secure: false,
      sameSite: "Lax" as const,
    }],
    origins: [{
      origin: WEB_ORIGIN,
      localStorage: [
        { name: "dothesis_access_token", value: token },
        { name: "dothesis_access_expires_at", value: String(expiresAt) },
      ],
    }],
  };
  fs.writeFileSync(path.join(AUTH_DIR, `${name}.json`), JSON.stringify(state, null, 2));
}

async function seedUser(rc: any, kind: string, stamp: number): Promise<Session> {
  // NB: use example.com, NOT a .test/.invalid/.localhost TLD — pydantic's
  // EmailStr (email-validator) rejects those reserved special-use domains
  // with a 422 at /auth/signup. example.com is the same domain the api pytest
  // suite seeds with, so it's known-good and needs no DNS/deliverability.
  const email = `e2e-${kind}-${stamp}@example.com`;
  const username = `e2e${kind}${stamp}`; // ^[a-zA-Z0-9_]{3,32}$ per auth.py
  const password = "e2e-password-123";
  await apiPost(rc, "/auth/signup", { username, email, password }); // REAL signup
  await apiPost(rc, "/test/verify-email", { email });               // the one seam
  const login = await apiPost(rc, "/auth/login", { email, password }); // REAL login
  return { email, password, token: login.access_token, expiresAt: login.expires_at };
}

setup("seed users and capture storage state", async ({ request }) => {
  fs.mkdirSync(AUTH_DIR, { recursive: true });
  const stamp = Date.now(); // unique per run — the DB is ephemeral anyway
  const main = await seedUser(request, "main", stamp);
  const broke = await seedUser(request, "broke", stamp);
  await apiPost(request, "/test/set-credit", { access_token: broke.token, credit: 0 });
  writeStorageState("user", main.token, main.expiresAt);
  writeStorageState("broke", broke.token, broke.expiresAt);
  fs.writeFileSync(
    path.join(AUTH_DIR, "session.json"),
    JSON.stringify({ main, broke }, null, 2),
  );
});
