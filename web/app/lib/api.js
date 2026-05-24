const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:7100/api/v1";

class ApiError extends Error {
  constructor(status, body) {
    // FastAPI wraps our { error: { code, message } } payload inside { detail: ... }.
    // Normalize so callers can always read `err.body.error.code`.
    const inner = body && typeof body.detail === "object" ? body.detail : body;
    // Prefer an explicit human message; if only a `code` is present, humanize it
    // (e.g. "insufficient_credit" -> "Insufficient credit") so the UI never shows
    // a bare "HTTP 402" pill.
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

export async function apiFetch(path, opts = {}) {
  const res = await fetch(BASE + path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
    body: opts.body && typeof opts.body !== "string" ? JSON.stringify(opts.body) : opts.body,
  });
  let body = null;
  try { body = await res.json(); } catch {}
  if (!res.ok) throw new ApiError(res.status, body);
  return body;
}

export function swrFetcher(path) {
  return apiFetch(path);
}

export function openEventStream(jobId, { since = 0, onEvent, onDone, onError } = {}) {
  const url = `${BASE}/jobs/${jobId}/events?since=${since}`;
  const es = new EventSource(url, { withCredentials: true });
  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      onEvent?.(data, e.lastEventId ? parseInt(e.lastEventId, 10) : null);
      // Terminal events: close so we stop holding the connection open.
      if (data.type === "job_done") { onDone?.(data); es.close(); }
      if (data.type === "error") { onError?.(data); es.close(); }
    } catch (err) {
      onError?.({ message: err.message });
    }
  };
  // DON'T close on transient errors — EventSource auto-reconnects on its own.
  // Closing here would mean a single dropped frame kills the live feed forever.
  es.onerror = () => {
    // Surface the blip to the UI as a soft notice, but keep the stream alive.
    onError?.({ message: "stream blip — auto-reconnecting", transient: true });
  };
  return () => es.close();
}

export { ApiError };
