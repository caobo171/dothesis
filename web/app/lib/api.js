// Tokens travel in the request body for POSTs. The API is POST-only, so the
// JWT never rides in a URL (it would otherwise leak into server access logs).
// The two browser-GET-only paths (SSE + file download) use a short-lived,
// resource-scoped stream token minted via /auth/stream-token instead.
// See web/app/lib/tokenStore.ts + api/app/jwt_auth.py for the design.
import { tokenStore } from "./tokenStore";

const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:7100/api/v1";

class ApiError extends Error {
  constructor(status, body) {
    const detail = body?.detail;

    // FastAPI request-validation errors (422) put an ARRAY under `detail`:
    //   [{ loc: ["body","password"], msg: "String should have at least 8…" }]
    // `typeof [] === "object"`, so the old code treated the array as our
    // { error: {…} } payload, found no message, and fell back to "HTTP 422".
    // Build a readable message from the field + msg of each validation error.
    let validationMsg = null;
    if (Array.isArray(detail)) {
      validationMsg = detail
        .map((e) => {
          const loc = Array.isArray(e?.loc) ? e.loc.filter((s) => s !== "body") : [];
          const field = loc.length ? loc[loc.length - 1] : null;
          const label = field
            ? String(field).charAt(0).toUpperCase() + String(field).slice(1)
            : null;
          return label && e?.msg ? `${label}: ${e.msg}` : e?.msg || null;
        })
        .filter(Boolean)
        .join("; ");
    }

    // Our own { error: { code, message } } payload, possibly wrapped in { detail }.
    // Only treat `detail` as that inner object when it is NOT the validation array.
    const inner =
      detail && typeof detail === "object" && !Array.isArray(detail) ? detail : body;
    const code = inner?.error?.code;
    const codeMsg = code
      ? String(code).replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
      : null;
    const msg =
      validationMsg ||
      inner?.error?.message ||
      (typeof inner?.detail === "string" ? inner.detail : null) ||
      (typeof detail === "string" ? detail : null) ||
      codeMsg ||
      `HTTP ${status}`;
    super(msg);
    this.status = status;
    this.body = inner || body || {};
  }
}

/**
 * Authenticated fetch. Injects access_token from tokenStore into the JSON body
 * (the API is POST-only, so the token never rides in a URL). Any `?query` in the
 * path is folded into the body too.
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
      // Authenticated GETs no longer exist (POST-only). The only GETs left are
      // unauthenticated (e.g. /health) or the SSE/download routes that mint a
      // scoped ?st= token (openEventStream / mintStreamToken) — we never put
      // the long-lived JWT in a URL here.
    } else {
      // POST family — fold any ?query from the path AND the token into the JSON
      // body, so SWR keys can keep their familiar `path?query` shape while the
      // token (and filters) stay out of the URL.
      const qIndex = url.indexOf("?");
      let qparams = {};
      if (qIndex >= 0) {
        qparams = Object.fromEntries(new URLSearchParams(url.slice(qIndex + 1)));
        url = url.slice(0, qIndex);
      }
      if (typeof body === "string") {
        try { body = JSON.parse(body); } catch { body = {}; }
      } else if (body == null) {
        body = {};
      }
      body = { ...qparams, ...body, access_token: token };
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

/** SWR fetcher. Reads are POST now (POST-only API): the token rides in the body
 * and any `?query` baked into the SWR key is folded into the body by apiFetch. */
export function swrFetcher(path) {
  return apiFetch(path, { method: "POST" });
}

/** Mint a short-lived token scoped to ONE resource, for a browser-GET endpoint
 * (SSE or <a download>) that can't carry a JSON body. */
export async function mintStreamToken(scope) {
  const { stream_token } = await apiFetch("/auth/stream-token", {
    method: "POST",
    body: { scope },
  });
  return stream_token;
}

/**
 * Download an M5 export (docx/pdf) given its project-scoped export URL.
 *
 * The /exports route is a browser GET that 302s to a signed S3 URL and still
 * requires auth — but <a download> can't carry a JSON body or Authorization
 * header. So we mint a short-lived, resource-scoped stream token and navigate
 * with ?st=, keeping the long-lived JWT out of the URL/logs. This is the same
 * path the ChatHeader + ContextPanel download buttons use; AutoDraftDrawer used
 * a raw <a href> with no token (and no API-base rewrite) and 401'd/404'd.
 *
 * `downloadUrl` is the export_artifacts download_url
 * (/api/v1/projects/{pid}/exports/{filename}). A URL that isn't a project
 * export (e.g. an already-signed S3 link) is opened as-is.
 */
export async function triggerExportDownload(downloadUrl) {
  if (!downloadUrl) return;
  const apiBase = process.env.NEXT_PUBLIC_API_BASE || "";
  const url = downloadUrl.startsWith("/api/v1/")
    ? `${apiBase}${downloadUrl.replace(/^\/api\/v1/, "")}`
    : downloadUrl;
  const m = downloadUrl.match(/\/projects\/([^/]+)\/exports\/([^/?]+)/);
  if (!m) {
    window.location.href = url;
    return;
  }
  const st = await mintStreamToken(`project-export:${m[1]}/${m[2]}`);
  const sep = url.includes("?") ? "&" : "?";
  window.location.href = `${url}${sep}st=${encodeURIComponent(st)}`;
}

/**
 * Download an uploaded file (PDF / .txt in Uploads panel) by upload id.
 *
 * Same trick as triggerExportDownload: mint a short-lived, resource-scoped
 * stream token and navigate to the GET /uploads/{id}/download route (which
 * 302s to a signed S3 URL). Browser saves the file under its original name
 * because the backend sets ResponseContentDisposition.
 */
export async function triggerUploadDownload(uploadId) {
  if (!uploadId) return;
  const apiBase = process.env.NEXT_PUBLIC_API_BASE || "";
  const st = await mintStreamToken(`project-upload:${uploadId}`);
  const base = apiBase || "/api/v1";
  window.location.href = `${base}/uploads/${uploadId}/download?st=${encodeURIComponent(st)}`;
}

/**
 * Job-event stream over EventSource. EventSource is GET-only and can't set a
 * body/header, AND it auto-reconnects by reopening the same URL — so auth rides
 * in the URL as a short-lived, job-scoped `?st=` stream token (never the
 * long-lived JWT). Minting is async, but we still return a synchronous cleanup
 * function so callers' useEffect teardown stays simple. For first-class SSE
 * (chat) the useStream hook uses fetch-streaming and pulls the token from a body.
 */
export function openEventStream(jobId, { since = 0, onEvent, onDone, onError } = {}) {
  let es = null;
  let closed = false;
  mintStreamToken(`job:${jobId}`)
    .then((st) => {
      if (closed) return;
      const url = `${BASE}/jobs/${jobId}/events?since=${since}&st=${encodeURIComponent(st)}`;
      es = new EventSource(url);
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
    })
    .catch((err) => { onError?.({ message: err.message }); });
  return () => { closed = true; es?.close(); };
}

export { ApiError };
