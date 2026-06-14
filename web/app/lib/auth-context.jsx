"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { apiFetch, ApiError } from "./api";
import { tokenStore } from "./tokenStore";

/**
 * @typedef {Object} AuthContextValue
 * @property {any} user
 * @property {boolean} loading
 * @property {(email: string, password: string) => Promise<any>} login
 * @property {(email: string, password: string) => Promise<any>} signup
 * @property {() => Promise<void>} logout
 * @property {(payload: any) => any} acceptTokenPayload
 */

/** @type {import('react').Context<AuthContextValue | null>} */
const AuthContext = createContext(null);

/**
 * Auth state for the React tree.
 *
 * Migration note: the backend used to set an dothesis_session cookie on
 * login. It now returns { user, access_token, expires_at } and the client
 * is responsible for persisting the token. See web/app/lib/tokenStore.ts.
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // On mount: if there's a stored token, fetch /auth/me to confirm it's
  // still valid and load the user row. apiFetch attaches the token; a
  // 401 inside apiFetch wipes the token AND throws, which we swallow
  // here (the user just falls through to logged-out state).
  useEffect(() => {
    if (!tokenStore.get()) {
      setLoading(false);
      return;
    }
    apiFetch("/auth/me", { method: "POST" })
      .then(setUser)
      .catch((e) => {
        if (!(e instanceof ApiError && e.status === 401)) console.error(e);
      })
      .finally(() => setLoading(false));
  }, []);

  const _savePayload = (payload) => {
    // Login / signup / verify / google all return TokenOut:
    // { user, access_token, expires_at }. Persist the token before
    // setting the user so subsequent apiFetch calls (e.g., a redirect
    // chain) can already auth.
    tokenStore.set(payload.access_token, payload.expires_at);
    setUser(payload.user);
    return payload.user;
  };

  const login = async (email, password) => {
    const payload = await apiFetch("/auth/login", {
      method: "POST",
      body: { email, password },
      auth: false,  // no token yet
    });
    return _savePayload(payload);
  };
  const signup = async (email, password) => {
    // Signup itself doesn't return a token (the user has to verify email
    // first). Keep the existing semantics — page redirects to wait-verify
    // and verify-page eventually calls /auth/verify which returns TokenOut.
    return apiFetch("/auth/signup", {
      method: "POST",
      body: { email, password },
      auth: false,
    });
  };
  const logout = async () => {
    // Best-effort — even if the API call fails (e.g., network), we still
    // want to wipe local state so the user sees a logged-out UI.
    try {
      await apiFetch("/auth/logout", { method: "POST", auth: false });
    } catch { /* swallow — local wipe is what matters */ }
    tokenStore.clear();
    setUser(null);
  };

  // Exposed so the verify page (which gets a TokenOut from /auth/verify)
  // and the Google sign-in flow can hand a payload back and finish login
  // without duplicating the persist logic.
  const acceptTokenPayload = (payload) => _savePayload(payload);

  return (
    <AuthContext.Provider value={{
      user, loading, login, signup, logout, acceptTokenPayload,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const v = useContext(AuthContext);
  if (!v) throw new Error("useAuth must be used inside <AuthProvider>");
  return v;
}
