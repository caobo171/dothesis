"use client";

import { useState } from "react";
import { ArrowLeft, Download } from "lucide-react";
import Link from "next/link";
import useSWR from "swr";

import { apiFetch } from "@/app/lib/api";
import { useT } from "@/app/lib/i18n/LocaleProvider";

import {
  triggerRunDiffDownload,
  triggerRunFileDownload,
} from "@/app/(inapp)/tools/_components/use-tool";

type Segment = { op: "equal" | "del" | "ins"; text: string };
type ParagraphDiff = { index: number; before: string; after: string; segments: Segment[] };
type RunDiff = {
  aligned: boolean;
  tool: string;
  filename: string | null;
  total: number;
  changed: number;
  unchanged: number;
  truncated: boolean;
  items: ParagraphDiff[];
};

/**
 * Inline diff of one paragraph.
 *
 * Removed text is struck through and kept ON SCREEN rather than hidden behind a
 * toggle: the question this page answers is "what did it change", and an answer
 * that shows only the new wording is the same as no answer.
 */
function Paragraph({ item }: { item: ParagraphDiff }) {
  return (
    <div className="rounded-xl border border-ink-100 p-4">
      <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-400">
        #{item.index + 1}
      </div>
      <p className="m-0 text-[13.5px] leading-relaxed text-ink-800">
        {item.segments.map((s, i) =>
          s.op === "equal" ? (
            <span key={i}>{s.text}</span>
          ) : s.op === "del" ? (
            <span key={i} className="rounded bg-[#FBE9E9] px-0.5 text-[#8A3A3A] line-through">
              {s.text}
            </span>
          ) : (
            <span key={i} className="rounded bg-[#E6F2E8] px-0.5 font-medium text-[#2F5136]">
              {s.text}
            </span>
          ),
        )}
      </p>
    </div>
  );
}

export default function RunDetail({ runId }: { runId: string }) {
  const t = useT();
  const [showAll, setShowAll] = useState(false);

  const { data, error, isLoading } = useSWR<RunDiff>(
    ["/tools/runs/diff", runId, showAll],
    () =>
      apiFetch(`/tools/runs/${runId}/diff`, {
        method: "POST",
        body: { changed_only: !showAll },
      }) as Promise<RunDiff>,
  );

  return (
    <section className="px-2 sm:px-4 lg:px-6">
      <div className="max-w-4xl mx-auto">
        <Link
          href="/tool-runs"
          className="inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-ink-500 hover:text-ink-800"
        >
          <ArrowLeft className="w-3.5 h-3.5" aria-hidden />
          {t("run.back")}
        </Link>

        <h1 className="mt-3 mb-1 text-base font-semibold text-ink-900">
          {data?.filename || t("run.title")}
        </h1>

        {error && <p className="text-[13px] text-[#8A3A3A]">{(error as Error).message}</p>}
        {isLoading && <p className="text-[13px] text-ink-500">{t("txn.loading")}</p>}

        {data && !data.aligned && (
          // Pairing across a length mismatch would attribute one paragraph's
          // words to another, so the comparison is refused rather than guessed.
          <p className="mt-3 rounded-lg border border-[#E8DCC0] bg-[#FBF6E9] px-3 py-2 text-[12.5px] text-[#7A5B2E]">
            {t("run.notAligned")}
          </p>
        )}

        {data && data.aligned && (
          <>
            <p className="mt-0 mb-4 text-[13px] text-ink-500">
              {t("run.summary", {
                changed: data.changed,
                unchanged: data.unchanged,
                total: data.total,
              })}
            </p>

            <div className="mb-4 flex flex-wrap items-center gap-2.5 text-[12.5px]">
              <button
                type="button"
                onClick={() => void triggerRunFileDownload(runId, "input")}
                className="rounded-full border border-ink-200 px-3 py-1.5 font-semibold text-primary-700 hover:bg-ink-50"
              >
                <Download className="mr-1 inline w-3.5 h-3.5" aria-hidden />
                {t("txn.tools.dlInput")}
              </button>
              <button
                type="button"
                onClick={() => void triggerRunFileDownload(runId, "output")}
                className="rounded-full border border-ink-200 px-3 py-1.5 font-semibold text-primary-700 hover:bg-ink-50"
              >
                <Download className="mr-1 inline w-3.5 h-3.5" aria-hidden />
                {t("txn.tools.dlOutput")}
              </button>
              {/* Exports carry the WHOLE document, changed and unchanged, because
                  a file read somewhere else has no "show unchanged" checkbox. */}
              <button
                type="button"
                onClick={() => void triggerRunDiffDownload(runId, "html")}
                className="rounded-full border border-ink-200 px-3 py-1.5 font-semibold text-ink-600 hover:bg-ink-50"
              >
                {t("run.exportHtml")}
              </button>
              <button
                type="button"
                onClick={() => void triggerRunDiffDownload(runId, "pdf")}
                className="rounded-full border border-ink-200 px-3 py-1.5 font-semibold text-ink-600 hover:bg-ink-50"
              >
                {t("run.exportPdf")}
              </button>
              <label className="ml-auto inline-flex cursor-pointer items-center gap-1.5 text-ink-600">
                <input
                  type="checkbox"
                  checked={showAll}
                  onChange={(e) => setShowAll(e.target.checked)}
                />
                {t("run.showUnchanged")}
              </label>
            </div>

            <div className="flex flex-col gap-2.5">
              {data.items.map((item) => (
                <Paragraph key={item.index} item={item} />
              ))}
            </div>

            {data.items.length === 0 && (
              <p className="text-[13px] text-ink-500">{t("run.noChanges")}</p>
            )}
            {data.truncated && (
              <p className="mt-3 text-[12px] text-ink-400">{t("run.truncated")}</p>
            )}
          </>
        )}
      </div>
    </section>
  );
}
