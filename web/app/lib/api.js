const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:7100/api/v1";

class ApiError extends Error {
  constructor(status, body) {
    super(body?.error?.message || `HTTP ${status}`);
    this.status = status;
    this.body = body;
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
      if (data.type === "job_done") { onDone?.(data); es.close(); }
      if (data.type === "error") { onError?.(data); es.close(); }
    } catch (err) {
      onError?.({ message: err.message });
    }
  };
  es.onerror = () => {
    onError?.({ message: "stream error" });
    es.close();
  };
  return () => es.close();
}

export { ApiError };
