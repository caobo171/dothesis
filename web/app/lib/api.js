// Tokens travel in the request body for POSTs, query string for GETs.
// See web/app/lib/tokenStore.ts + api/app/jwt_auth.py for the design.
import { tokenStore } from "./tokenStore";

const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:7100/api/v1";

class ApiError extends Error {
  constructor(status, body) {
    // FastAPI wraps our { error: { code, message } } payload inside { detail: ... }.
    // Normalize so callers can always read `err.body.error.code`.
    const inner = body && typeof body.detail === "object" ? body.detail : body;
    const code = inner?.error?.code;
    const codeMsg = code
      ? String(code).replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
      : null;
    const msg =
      inner?.error?.message ||
      (typeof inner?.detail === "string" ? inner.detail : null) ||
      codeMsg ||
      `HTTP ${status}`;
    super(msg);
    this.status = status;
    this.body = inner || body || {};
  }
}

/**
 * Authenticated fetch. Injects access_token from tokenStore:
 *   - POST/PUT/PATCH/DELETE → into the JSON body
 *   - GET → into the query string (?access_token=…)
 *
 * Auth endpoints (login/signup/forgot-password/etc.) don't have a token
 * yet, so they pass `{ auth: false }` to skip injection.
 *
 * Drops credentials: "include" because we no longer use cookies for auth.
 * The 401-on-bad-token handler clears tokenStore and redirects to /login
 * so a stale token can't silently keep failing on every call.
 */
export async function apiFetch(path, opts = {}) {
  const { auth = true, ...rest } = opts;
  const token = auth ? tokenStore.get() : null;
  const method = (rest.method || "GET").toUpperCase();

  let url = BASE + path;
  let body = rest.body;

  if (token) {
    if (method === "GET" || method === "HEAD") {
      const sep = url.includes("?") ? "&" : "?";
      url = `${url}${sep}access_token=${encodeURIComponent(token)}`;
    } else {
      // POST family — fold the token into the JSON body. If the caller
      // already passed a JSON string, parse / merge / re-stringify.
      if (typeof body === "string") {
        try { body = JSON.parse(body); } catch { body = {}; }
      } else if (body == null) {
        body = {};
      }
      body = { ...body, access_token: token };
    }
  }

  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(rest.headers || {}) },
    ...rest,
    body: typeof body === "string" || body == null ? body : JSON.stringify(body),
  });

  let parsed = null;
  try { parsed = await res.json(); } catch { /* tolerate empty 204s */ }

  if (!res.ok) {
    // 401 always wipes the stored token AND forces a redirect to /login.
    // Why redirect here instead of letting the UI handle it: an expired
    // token cascades — every SWR fetcher on the page hits 401 and the
    // dev.sh stderr fills with 401s while the UI sits there. Pulling the
    // ripcord at the fetch layer breaks the cascade immediately.
    //
    // Guards:
    //   - `auth: false` calls (login/signup/verify) never trigger redirect.
    //     Those endpoints' 401s are user-visible "wrong password" errors,
    //     not auth-expired signals.
    //   - SSR/Node contexts have no `window`; skip the navigation there.
    //   - Already on /login? Don't loop-redirect to itself.
    if (res.status === 401 && auth) {
      tokenStore.clear();
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
        const next = encodeURIComponent(window.location.pathname + window.location.search);
        window.location.href = `/login?next=${next}`;
        // Throw anyway so any in-flight `.then` doesn't try to dereference
        // the parsed body — the navigation will tear down the page first
        // but `throw` ensures the local promise rejects cleanly.
      }
    }
    throw new ApiError(res.status, parsed);
  }
  return parsed;
}

/** SWR fetcher uses GET semantics — the token rides in the query string. */
export function swrFetcher(path) {
  return apiFetch(path);
}

/**
 * Job-event stream. Used to ride on EventSource + a cookie; EventSource
 * can't set custom headers and doesn't expose a way to put the token in
 * a POST body either. We pass the token via the URL so EventSource's
 * built-in reconnection still works. For first-class SSE (chat) the
 * useStream hook uses fetch-streaming and pulls the token from the body.
 */
export function openEventStream(jobId, { since = 0, onEvent, onDone, onError } = {}) {
  const token = tokenStore.get();
  const tokenParam = token ? `&access_token=${encodeURIComponent(token)}` : "";
  const url = `${BASE}/jobs/${jobId}/events?since=${since}${tokenParam}`;
  // withCredentials removed: no cookie-based auth left.
  const es = new EventSource(url);
  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      onEvent?.(data, e.lastEventId ? parseInt(e.lastEventId, 10) : null);
      if (data.type === "job_done") { onDone?.(data); es.close(); }
      if (data.type === "error") { onError?.(data); es.close(); }
    } catch (err) {
      onError?.({ message: err.message });
    }
  };
  es.onerror = () => {
    onError?.({ message: "stream blip — auto-reconnecting", transient: true });
  };
  return () => es.close();
}

export { ApiError };
