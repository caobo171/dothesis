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
): Promise<{
  blob: Blob; filename: string; credits: number | null;
  resolved: number | null; unresolved: number | null; weak: number | null;
  uncited: number | null;
  added: number | null; marked: number | null; linked: number | null;
}> {
  const res = await postFile(`/tools/document/cite?add_missing=${addMissing}`, file);
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
): Promise<{ blob: Blob; filename: string; credits: number | null; rewritten: number | null }> {
  const res = await postFile("/tools/document/humanize", file);
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
  };
}
