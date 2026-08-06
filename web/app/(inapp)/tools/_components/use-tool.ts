"use client";

import { useCallback, useRef, useState } from "react";

import { apiFetch } from "@/app/lib/api";
import { useT } from "@/app/lib/i18n/LocaleProvider";
import type { MessageKey } from "@/app/lib/i18n/messages/en";
import type { TParams } from "@/app/lib/i18n/locale";

/**
 * A translator, passed in.
 *
 * The helpers below run at module scope — they cannot call useT(), and their
 * failures are the ones a student actually sees ("that file is too large"), so
 * leaving them in English would put English error text inside a Vietnamese
 * form. Every caller is a client component that already holds `t`.
 */
export type Translate = (key: MessageKey, params?: TParams) => string;

/**
 * One request/response cycle against a stateless tool endpoint.
 *
 * These endpoints (POST /humanize, /tools/writing-rhythm, /tools/verify-citation)
 * already existed and are what the MCP connector calls — text in, answer out, no
 * project, no thread, no agent turn. The web app was the only surface that
 * couldn't reach them, so this is a door onto primitives that already work,
 * not a second implementation of them.
 *
 * Deliberately not SWR: these are user-triggered mutations, not cached reads.
 * Re-running the same passage must actually re-run it (a rewrite is
 * non-deterministic), which is exactly what SWR's dedupe would prevent.
 */
export function useTool<TOut>(path: string) {
  const [result, setResult] = useState<TOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Guards against an out-of-order response overwriting a newer one: a student
  // who edits and re-submits while the first call is still open would otherwise
  // see the stale answer land on top of the fresh one.
  const seq = useRef(0);
  const t = useT();

  const run = useCallback(
    async (body: Record<string, unknown>) => {
      const mine = ++seq.current;
      setBusy(true);
      setError(null);
      try {
        const data = (await apiFetch(path, { method: "POST", body })) as TOut;
        if (mine === seq.current) setResult(data);
        return data;
      } catch (e) {
        if (mine === seq.current) {
          setError((e as Error)?.message || t("tools.err.request"));
          setResult(null);
        }
        return null;
      } finally {
        if (mine === seq.current) setBusy(false);
      }
    },
    [path, t],
  );

  const reset = useCallback(() => {
    seq.current++;  // orphan any in-flight call so it can't repopulate
    setResult(null);
    setError(null);
    setBusy(false);
  }, []);

  return { result, error, busy, run, reset };
}

/**
 * Extract text from a PDF / .docx / .txt via POST /tools/extract-text.
 *
 * Raw fetch with a Bearer header, NOT apiFetch: apiFetch folds the token into a
 * JSON body and sets Content-Type: application/json, which multipart cannot
 * use. Same shape as the /new page's uploadOne, which is the established
 * pattern for authenticated file posts here.
 *
 * Nothing is stored server-side — the file is a transport for one passage.
 */
export async function extractFileText(file: File, t: Translate): Promise<string> {
  const { tokenStore } = await import("@/app/lib/tokenStore");
  const token = tokenStore.get();
  const base = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:7100/api/v1";
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${base}/tools/extract-text`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: fd,
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(
      body?.detail?.error?.message ||
        (res.status === 415
          ? t("tools.err.unsupported")
          : res.status === 413
            ? t("tools.err.tooLarge")
            : t("tools.err.readFile", { status: res.status })),
    );
  }
  if (!body?.ok) throw new Error(body?.detail || t("tools.err.noText"));
  return body.text as string;
}

/**
 * Bearer + multipart, shared by the document routes.
 *
 * `timeoutMs` is not optional decoration: the document routes hold one request
 * open for the whole walk, and a fetch whose connection dies mid-flight (the
 * API worker restarting under it — a dev `--reload`, a deploy) can hang
 * forever instead of rejecting. Without a deadline the caller's spinner has no
 * exit at all, which is exactly what a student saw: "Đang viết lại…" with a
 * dead socket behind it. Pass a bound generous enough for the real job; the
 * point is that one exists.
 */
async function postFile(path: string, file: File, timeoutMs?: number): Promise<Response> {
  const { tokenStore } = await import("@/app/lib/tokenStore");
  const token = tokenStore.get();
  const base = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:7100/api/v1";
  const fd = new FormData();
  fd.append("file", file);
  return fetch(`${base}${path}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: fd,
    signal: timeoutMs ? AbortSignal.timeout(timeoutMs) : undefined,
  });
}

/**
 * How long a document walk may take before we call it dead.
 *
 * Scaled by the batch count the free scan already reported, because "too long"
 * for a 3-passage abstract and for a 70-passage thesis are different numbers by
 * an order of magnitude. 3 minutes per batch is deliberately loose — a batch is
 * one reasoning-model call and the provider SDK's own per-call ceiling is 10
 * minutes — so this fires for a connection that has actually died, not for a
 * run that is merely slow. Cancelling real work the student is billed for is
 * the worse failure of the two.
 */
function docTimeoutMs(passages: number | null | undefined): number {
  return 120_000 + Math.max(1, passages || 1) * 180_000;
}

/**
 * Turn a failed document fetch into something a student can act on.
 *
 * A timeout and a dropped connection both arrive here as exceptions with no
 * HTTP status, and both used to surface as nothing at all — the spinner simply
 * never stopped. They mean different things ("still running, we stopped
 * waiting" vs "the server went away"), so they get different messages.
 */
function docRequestError(e: unknown, t: Translate): Error {
  const name = (e as Error)?.name;
  if (name === "TimeoutError" || name === "AbortError") {
    return new Error(t("tools.err.docTimeout"));
  }
  if (e instanceof TypeError) return new Error(t("tools.err.docConnection"));
  return e instanceof Error ? e : new Error(t("tools.err.request"));
}

/**
 * Send the browser to a run's stored input or output .docx.
 *
 * Same shape as triggerUploadDownload: mint a token scoped to this exact run
 * AND half, then navigate. The scope names the half so a leaked URL opens one
 * file rather than both.
 */
export async function triggerRunFileDownload(runId: string, which: "input" | "output") {
  const { mintStreamToken } = await import("@/app/lib/api");
  const apiBase = process.env.NEXT_PUBLIC_API_BASE || "";
  const st = await mintStreamToken(`tool-run-file:${runId}/${which}`);
  const base = apiBase || "/api/v1";
  window.location.href =
    `${base}/tools/runs/${runId}/file/${which}?st=${encodeURIComponent(st)}`;
}

/** Delete a run's stored files now, without waiting out the retention window. */
export async function deleteRunFiles(runId: string): Promise<number> {
  const r = (await apiFetch(`/tools/runs/${runId}/files/delete`, {
    method: "POST", body: {},
  })) as { deleted?: number };
  return r?.deleted ?? 0;
}

export type RunProgress = { status: string; done: number; total: number };

/** Where a run has got to. Polled while a document walk is open. */
export async function fetchRunProgress(runId: string): Promise<RunProgress | null> {
  try {
    return (await apiFetch(`/tools/runs/${runId}/progress`, {
      method: "POST", body: {},
    })) as RunProgress;
  } catch {
    // A progress poll that fails must never surface as a run failure — the
    // rewrite is still going, we just cannot say how far along it is.
    return null;
  }
}

/**
 * Run a stored document through its tool again.
 *
 * Billed like any other run, because it is one: the model does the work again
 * in full. The caller is responsible for saying so before it fires.
 */
export async function rerunToolRun(
  runId: string,
  filename: string,
  t: Translate,
  passages?: number | null,
): Promise<{ blob: Blob; filename: string; credits: number | null }> {
  const { tokenStore } = await import("@/app/lib/tokenStore");
  const token = tokenStore.get();
  const base = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:7100/api/v1";
  let res: Response;
  try {
    res = await fetch(`${base}/tools/runs/${runId}/rerun`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access_token: token }),
      // The original run recorded its own batch count, so the deadline is the
      // same one that run had. Falling back to 60 rather than to 1 for a row
      // that predates progress tracking: guessing "one batch" would abort a
      // thesis re-run after five minutes, and a deadline that is too generous
      // only delays an error message, while one that is too tight destroys
      // work the student is paying for.
      signal: AbortSignal.timeout(docTimeoutMs(passages || 60)),
    });
  } catch (e) {
    throw docRequestError(e, t);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(
      body?.detail?.error?.message || t("tools.err.rewriteFailed", { status: res.status }),
    );
  }
  const v = res.headers.get("X-Credits-Charged");
  return {
    blob: await res.blob(),
    filename,
    credits: v === null ? null : Number(v),
  };
}

export type DocScan = {
  ok: boolean;
  body_paragraphs: number;
  headings: number;
  short_or_captions: number;
  tables: number;
  passages: number;
  chars: number;
};

/** What a rewrite would touch. No LLM, no charge — this is the confirm step. */
export async function scanDocument(file: File, t: Translate): Promise<DocScan> {
  const res = await postFile("/tools/document/scan", file);
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(
      body?.detail?.error?.message ||
        (res.status === 415
          ? t("tools.err.needDocx")
          : t("tools.err.readDoc", { status: res.status })),
    );
  }
  return body as DocScan;
}

export type CiteScan = {
  ok: boolean;
  /** Phase A's price in credits, quoted before it runs. Phase B is token-billed. */
  resolve_cost: number;
  intext_citations: number;
  distinct_sources: number;
  existing_references: number;
  has_reference_section: boolean;
  body_paragraphs: number;
  passages: number;
  headings: number;
  tables: number;
};

/** What citing would touch. Free — no model runs. */
export async function scanCiteDocument(file: File, t: Translate): Promise<CiteScan> {
  const res = await postFile("/tools/document/cite/scan", file);
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(
      body?.detail?.error?.message ||
        (res.status === 415
          ? t("tools.err.needDocx")
          : t("tools.err.readDoc", { status: res.status })),
    );
  }
  return body as CiteScan;
}

/**
 * Run the citer and hand back the .docx.
 *
 * `addMissing` rides in the query string because the body is multipart — this
 * is the one place in the app where a flag can't travel in JSON. The counts
 * come back in headers for the same reason the humanize route uses them: a
 * streamed file cannot also carry a JSON body.
 */
export async function citeDocument(
  file: File,
  addMissing: boolean,
  t: Translate,
  passages?: number | null,
): Promise<{
  blob: Blob; filename: string; credits: number | null;
  resolved: number | null; unresolved: number | null; weak: number | null;
  uncited: number | null;
  added: number | null; marked: number | null; linked: number | null;
}> {
  let res: Response;
  try {
    // Same deadline as the rewrite: this route holds one request open across a
    // CrossRef lookup per source plus phase B's model calls.
    res = await postFile(
      `/tools/document/cite?add_missing=${addMissing}`, file, docTimeoutMs(passages));
  } catch (e) {
    throw docRequestError(e, t);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(
      body?.detail?.error?.message || t("tools.cite.errFailed"),
    );
  }
  const num = (h: string) => {
    const v = res.headers.get(h);
    return v === null ? null : Number(v);
  };
  const stem = file.name.replace(/\.docx$/i, "");
  return {
    blob: await res.blob(),
    filename: `${stem}-cited.docx`,
    credits: num("X-Credits-Charged"),
    resolved: num("X-Citations-Resolved"),
    unresolved: num("X-Citations-Unresolved"),
    weak: num("X-Citations-Weak"),
    uncited: num("X-References-Uncited"),
    added: num("X-Citations-Added"),
    marked: num("X-Claims-Marked"),
    linked: num("X-Citations-Linked"),
  };
}

/**
 * Run the rewrite and hand back the .docx.
 *
 * The response is a FILE, so the counts ride in headers — a streamed document
 * cannot also carry a JSON body. Header reads are null-safe because
 * Access-Control-Expose-Headers may not list them on every deployment; the
 * charge is in token_ledger regardless, so a missing header costs a label, not
 * an audit trail.
 */
export async function humanizeDocument(
  file: File,
  t: Translate,
  passages?: number | null,
): Promise<{
  blob: Blob; filename: string; credits: number | null;
  rewritten: number | null; skipped: number | null;
}> {
  let res: Response;
  try {
    res = await postFile("/tools/document/humanize", file, docTimeoutMs(passages));
  } catch (e) {
    throw docRequestError(e, t);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(
      body?.detail?.error?.message || t("tools.err.rewriteFailed", { status: res.status }),
    );
  }
  const num = (h: string) => {
    const v = res.headers.get(h);
    return v === null ? null : Number(v);
  };
  const stem = file.name.replace(/\.docx$/i, "");
  return {
    blob: await res.blob(),
    filename: `${stem}-humanized.docx`,
    credits: num("X-Credits-Charged"),
    rewritten: num("X-Paragraphs-Rewritten"),
    // Read at last: the server has always sent this and the client always
    // dropped it, so a run where the provider failed on half the batches
    // reported only its successes and the student had to diff the file to find
    // out. They paid for those attempts; they get told about them.
    skipped: num("X-Paragraphs-Skipped"),
  };
}
