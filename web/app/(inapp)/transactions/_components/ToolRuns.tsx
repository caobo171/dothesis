"use client";

import { useState } from "react";
import { Wrench } from "lucide-react";
import useSWR from "swr";

import { apiFetch } from "@/app/lib/api";
import { useT } from "@/app/lib/i18n/LocaleProvider";
import type { MessageKey } from "@/app/lib/i18n/messages/en";
import {
  deleteRunFiles,
  rerunToolRun,
  triggerRunFileDownload,
} from "@/app/(inapp)/tools/_components/use-tool";

/**
 * The caller's own tool history.
 *
 * Sits next to the transaction list rather than inside it because it is NOT the
 * same list. A run that charged nothing writes no credit transaction at all —
 * the free tools, a failed run, and the one that actually matters: a run whose
 * cost the balance could not cover. Those rows are invisible in a debit ledger,
 * and they are precisely what a student is looking for when they ask why their
 * credits moved, or why they didn't.
 */

type Run = {
  id: string;
  tool: string;
  ok: boolean;
  error: string | null;
  units: number;
  credits_charged: number;
  credits_cost: number;
  created_at: string;
  has_input: boolean;
  has_output: boolean;
  files_expire_at: string | null;
  metrics: { rewritten?: number; skipped?: number } | null;
  parent_run_id: string | null;
  status: string;
  progress_done: number;
  progress_total: number;
};

type RunsResp = { items: Run[]; total: number; page: number; page_size: number };

// Tool slug → label key. Server-side slugs are stable identifiers, not copy, so
// the mapping lives here where the rest of the UI's wording does.
const TOOL_KEY: Record<string, MessageKey> = {
  "humanize": "txn.tool.humanize",
  "humanize-docx": "txn.tool.humanizeDocx",
  "cite-docx": "txn.tool.citeDocx",
  "verify-citation": "txn.tool.verifyCitation",
  "verify-citations": "txn.tool.verifyCitations",
  "writing-rhythm": "txn.tool.rhythm",
  "plagiarism-check": "txn.tool.plagiarism",
  "extract-text": "txn.tool.extractText",
  "scan-docx": "txn.tool.scanDocx",
  "scan-cite-docx": "txn.tool.scanCiteDocx",
};

const PAGE_SIZE = 20;

// Only the tools that take a file in and give a file back can be run again.
// Mirrors the server's own check, which is the one that actually enforces it.
const RERUNNABLE = new Set(["humanize-docx", "cite-docx"]);

export default function ToolRuns() {
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const t = useT();

  const body = { page, page_size: PAGE_SIZE };
  const { data, isLoading, mutate } = useSWR<RunsResp>(
    ["/tools/runs", page],
    () => apiFetch("/tools/runs", { method: "POST", body }) as Promise<RunsResp>,
    {
      // While something is running, the list IS the progress display — poll it
      // so "12/70" advances without the student reloading the page.
      refreshInterval: (latest) =>
        latest?.items?.some((r) => r.status === "running") ? 3000 : 0,
    },
  );

  const removeFiles = async (r: Run) => {
    // Confirmed because it is irreversible and the row it acts on looks like a
    // read-only history line.
    if (!window.confirm(t("txn.tools.deleteConfirm"))) return;
    setBusy(r.id);
    setError(null);
    try {
      await deleteRunFiles(r.id);
      void mutate();
    } catch (e) {
      setError((e as Error)?.message || t("tools.err.request"));
    } finally {
      setBusy(null);
    }
  };

  const rerun = async (r: Run) => {
    // A re-run costs credits. Saying so before it fires, not after, because the
    // button sits one click away in a list the student opened to ask about
    // their credits in the first place.
    if (!window.confirm(t("txn.tools.rerunConfirm"))) return;
    setBusy(r.id);
    setError(null);
    try {
      const out = await rerunToolRun(r.id, `rerun-${r.id}.docx`, t, r.progress_total);
      const url = URL.createObjectURL(out.blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = out.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      void mutate();
    } catch (e) {
      setError((e as Error)?.message || t("tools.err.request"));
    } finally {
      setBusy(null);
    }
  };

  const pages = data ? Math.ceil(data.total / data.page_size) : 1;

  return (
    // No heading of its own any more: the tab above already says what this is,
    // and repeating it cost a whole screen of vertical space before the first row.
    <div>
      <p className="mt-0 mb-4 flex items-start gap-2 text-[13px] text-ink-500">
        <Wrench className="mt-0.5 w-4 h-4 shrink-0 text-ink-400" aria-hidden />
        <span>{t("txn.tools.blurb")}</span>
      </p>

      {error && (
        <p className="mb-3 rounded-lg border border-[#E6C9C9] bg-[#FBF0F0] px-3 py-2 text-[12.5px] text-[#8A3A3A]">
          {error}
        </p>
      )}

      {data && data.items.length > 0 ? (
        <>
          <div className="overflow-x-auto rounded-xl border border-ink-100">
            <table className="w-full text-sm">
              <thead className="bg-ink-50 text-ink-500 text-xs uppercase tracking-wide">
                <tr>
                  <th className="text-left font-medium px-4 py-2">{t("txn.col.date")}</th>
                  <th className="text-left font-medium px-4 py-2">{t("txn.col.tool")}</th>
                  <th className="text-left font-medium px-4 py-2">{t("txn.col.result")}</th>
                  <th className="text-right font-medium px-4 py-2">{t("txn.col.credits")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {data.items.map((r) => {
                  const key = TOOL_KEY[r.tool];
                  const shortfall = r.credits_cost - r.credits_charged;
                  return (
                    <tr key={r.id} className="hover:bg-ink-50/50">
                      <td className="px-4 py-2 text-ink-500 whitespace-nowrap">
                        {new Date(r.created_at).toLocaleString()}
                      </td>
                      <td className="px-4 py-2 text-ink-900">
                        {key ? t(key) : r.tool}
                        {r.units > 0 && (
                          <span className="ml-1.5 text-xs text-ink-400">
                            {t("txn.tools.units", { count: r.units })}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2">
                        {r.status === "running"
                          ? <span className="text-ink-600 tabular-nums">
                              {r.progress_total > 0
                                ? t("txn.tools.running", {
                                    done: r.progress_done, total: r.progress_total })
                                : t("txn.tools.runningPlain")}
                            </span>
                          : r.ok
                            ? <span className="text-[#3A5740]">{t("txn.tools.ok")}</span>
                            : <span className="text-[#8E6B2A]">{t("txn.tools.failed")}</span>}
                        {/* A partial run used to be indistinguishable from a
                            clean one: the counts rode out in a response header
                            and were never stored. */}
                        {typeof r.metrics?.skipped === "number" && r.metrics.skipped > 0 && (
                          <div className="text-[11px] text-[#8E6B2A]">
                            {t("txn.tools.partial", {
                              done: r.metrics.rewritten ?? 0,
                              skipped: r.metrics.skipped,
                            })}
                          </div>
                        )}
                        {(r.has_input || r.has_output) && (
                          <div className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11.5px]">
                            {r.has_input && (
                              <button type="button"
                                onClick={() => void triggerRunFileDownload(r.id, "input")}
                                className="font-semibold text-primary-700 hover:text-primary-800">
                                {t("txn.tools.dlInput")}
                              </button>
                            )}
                            {r.has_output && (
                              <button type="button"
                                onClick={() => void triggerRunFileDownload(r.id, "output")}
                                className="font-semibold text-primary-700 hover:text-primary-800">
                                {t("txn.tools.dlOutput")}
                              </button>
                            )}
                            {r.has_input && RERUNNABLE.has(r.tool) && (
                              <button type="button"
                                disabled={busy === r.id}
                                onClick={() => void rerun(r)}
                                className="font-semibold text-primary-700 hover:text-primary-800 disabled:opacity-40">
                                {busy === r.id ? t("txn.tools.rerunning") : t("txn.tools.rerun")}
                              </button>
                            )}
                            <button type="button"
                              disabled={busy === r.id}
                              onClick={() => void removeFiles(r)}
                              className="text-ink-400 hover:text-[#8A3A3A] disabled:opacity-40">
                              {t("txn.tools.deleteFiles")}
                            </button>
                            {r.files_expire_at && (
                              <span className="text-ink-400">
                                {t("txn.tools.keptUntil", {
                                  date: new Date(r.files_expire_at).toLocaleDateString(),
                                })}
                              </span>
                            )}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums">
                        {r.credits_charged > 0
                          ? <span className="font-semibold text-red-600">
                              −{r.credits_charged.toLocaleString()}
                            </span>
                          : <span className="text-ink-400">{t("txn.tools.free")}</span>}
                        {/* Only when the balance couldn't cover it. A student
                            whose credits ran out mid-document should learn it
                            here, not as a surprise on the next run. */}
                        {shortfall > 0 && (
                          <div className="text-[11px] text-[#8E6B2A]">
                            {t("txn.tools.shortfall", { count: shortfall })}
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {pages > 1 && (
            <div className="mt-3 flex items-center justify-end gap-2 text-[13px]">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="rounded-lg border border-ink-200 px-3 py-1.5 font-semibold text-ink-600 disabled:opacity-40 hover:bg-ink-50"
              >
                {t("txn.prev")}
              </button>
              <span className="text-ink-500 tabular-nums">{page} / {pages}</span>
              <button
                type="button"
                disabled={page >= pages}
                onClick={() => setPage((p) => p + 1)}
                className="rounded-lg border border-ink-200 px-3 py-1.5 font-semibold text-ink-600 disabled:opacity-40 hover:bg-ink-50"
              >
                {t("txn.next")}
              </button>
            </div>
          )}
        </>
      ) : (
        <p className="text-sm text-ink-500">
          {isLoading ? t("txn.loading") : t("txn.tools.empty")}
        </p>
      )}
    </div>
  );
}
