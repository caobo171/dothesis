"use client";

import { useCallback, useRef, useState } from "react";

import { apiFetch } from "@/app/lib/api";

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
          setError((e as Error)?.message || "Request failed.");
          setResult(null);
        }
        return null;
      } finally {
        if (mine === seq.current) setBusy(false);
      }
    },
    [path],
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
export async function extractFileText(file: File): Promise<string> {
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
          ? "That file type isn't supported — use PDF, Word or a text file."
          : res.status === 413
            ? "That file is too large."
            : `Could not read the file (${res.status}).`),
    );
  }
  if (!body?.ok) throw new Error(body?.detail || "No text could be read from this file.");
  return body.text as string;
}

/** Bearer + multipart, shared by the document routes. */
async function postFile(path: string, file: File): Promise<Response> {
  const { tokenStore } = await import("@/app/lib/tokenStore");
  const token = tokenStore.get();
  const base = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:7100/api/v1";
  const fd = new FormData();
  fd.append("file", file);
  return fetch(`${base}${path}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: fd,
  });
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
export async function scanDocument(file: File): Promise<DocScan> {
  const res = await postFile("/tools/document/scan", file);
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(
      body?.detail?.error?.message ||
        (res.status === 415
          ? "Document rewriting needs a .docx — a PDF has no editable paragraphs."
          : `Could not read the document (${res.status}).`),
    );
  }
  return body as DocScan;
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
): Promise<{ blob: Blob; filename: string; credits: number | null; rewritten: number | null }> {
  const res = await postFile("/tools/document/humanize", file);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(
      body?.detail?.error?.message || `The rewrite did not complete (${res.status}).`,
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
  };
}
