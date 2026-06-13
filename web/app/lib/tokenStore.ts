/**
 * Access-token store — replaces the dothesis_session cookie path.
 *
 * Storage:
 *   - localStorage: the canonical token. Read on every authenticated fetch.
 *   - Cookie mirror (non-HTTPOnly, SameSite=Lax): used ONLY by Next.js
 *     middleware (proxy.js) which runs server-side and can't read
 *     localStorage. The cookie carries a "logged-in marker" of the same
 *     token; the middleware checks its presence to gate routes, not to
 *     authenticate API calls. The API still reads the token from the
 *     request body (see api/app/jwt_auth.py + deps.py).
 *
 * Why both: pure localStorage would force every protected route to do a
 * client-side useEffect check + flash unauth content before redirect. The
 * cookie marker lets the middleware redirect server-side, eliminating the
 * flash. Token still doesn't ride on the API call via cookies — it rides
 * in the JSON body.
 */
const KEY_ACCESS = "dothesis_access_token";
const KEY_EXPIRES = "dothesis_access_expires_at";

// SameSite=Lax means the cookie travels on top-level navigation (so the
// middleware sees it) but NOT on cross-site iframe / form posts —
// reasonable hardening for a non-HTTPOnly marker that isn't auth-critical.
const COOKIE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60;

function safeWindow(): Window | null {
  return typeof window !== "undefined" ? window : null;
}

export const tokenStore = {
  /** Save a fresh token from a login/signup/verify response. */
  set(token: string, expiresAtEpoch: number): void {
    const w = safeWindow();
    if (!w) return;
    w.localStorage.setItem(KEY_ACCESS, token);
    w.localStorage.setItem(KEY_EXPIRES, String(expiresAtEpoch));
    // Cookie mirror. URL-encode the token so any '+'/'/' in base64url
    // segments survives the round-trip (Cookie syntax forbids them raw).
    document.cookie =
      `${KEY_ACCESS}=${encodeURIComponent(token)};` +
      ` path=/; max-age=${COOKIE_MAX_AGE_SECONDS}; SameSite=Lax`;
  },

  /** Read the token, or null if missing/expired (we DON'T verify the JWT
   *  signature on the client — only the obvious expiry check). */
  get(): string | null {
    const w = safeWindow();
    if (!w) return null;
    const token = w.localStorage.getItem(KEY_ACCESS);
    if (!token) return null;
    const expRaw = w.localStorage.getItem(KEY_EXPIRES);
    if (expRaw) {
      const exp = Number(expRaw);
      if (Number.isFinite(exp) && exp * 1000 < Date.now()) {
        // Expired — wipe and report missing so the caller goes to /login.
        // Better to be honest about expiry than let the backend 401 first.
        this.clear();
        return null;
      }
    }
    return token;
  },

  /** Expire-window check without returning the token. Callers that just
   *  want to gate UI ("show user menu") use this to avoid a localStorage
   *  read every render. */
  isLoggedIn(): boolean {
    return this.get() !== null;
  },

  /** Drop the token from both storages — logout, or 401 from the API. */
  clear(): void {
    const w = safeWindow();
    if (!w) return;
    w.localStorage.removeItem(KEY_ACCESS);
    w.localStorage.removeItem(KEY_EXPIRES);
    document.cookie =
      `${KEY_ACCESS}=; path=/; max-age=0; SameSite=Lax`;
  },
};

/** Cookie name the Next.js middleware looks for. Exported so proxy.js stays
 *  in sync with the keys here — one source of truth. */
export const TOKEN_COOKIE_NAME = KEY_ACCESS;
