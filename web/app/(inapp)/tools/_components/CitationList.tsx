"use client";

import { useState } from "react";
import { CheckCircle2, HelpCircle, XCircle } from "lucide-react";

import { useT, useTn } from "@/app/lib/i18n/LocaleProvider";

import { useTool } from "./use-tool";
import { ToolTextarea, RunButton, ToolError, FileDrop } from "./shell";

type CitationItem = {
  reference: string;
  ok: boolean;
  found: boolean;
  doi: string | null;
  title: string | null;
  authors: string | null;
  year: number | null;
  container: string | null;
  matched_by: string | null;
  warning: string | null;
  detail: string | null;
};

type CitationListOut = {
  ok: boolean;
  detected: number;
  checked: number;
  truncated: boolean;
  items: CitationItem[];
  detail: string | null;
};

/**
 * Check every reference in a document at once.
 *
 * This exists because of what students actually did with the single-reference
 * box: they attached the finished thesis. That could never work — the single
 * endpoint sends only the first 400 characters to CrossRef, so a chapter came
 * back matched against an unrelated paper — and the 2000-character cap turned
 * it into a raw validation error instead of an explanation.
 *
 * Verdicts are rendered from the response's own `matched_by` / `found` fields
 * using the same three labels as the single check, so a reference cannot read
 * as more confirmed here than it would there.
 */
export function CitationList() {
  const [text, setText] = useState("");
  const [fileBusy, setFileBusy] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const { result, error, busy, run } = useTool<CitationListOut>("/tools/verify-citations");
  const t = useT();
  const tn = useTn();

  const items = result?.items ?? [];
  const confirmed = items.filter((i) => i.found && i.matched_by === "doi").length;
  const probable = items.filter((i) => i.found && i.matched_by !== "doi").length;
  const missing = items.filter((i) => i.ok && !i.found).length;

  return (
    <div className="flex flex-col gap-4">
      <FileDrop
        onText={setText}
        busy={fileBusy}
        setBusy={setFileBusy}
        onError={setFileError}
      />
      <ToolError message={fileError} />
      <ToolTextarea
        label={t("tools.citation.listLabel")}
        value={text}
        onChange={setText}
        rows={8}
        placeholder={t("tools.citation.listPlaceholder")}
      />

      <div>
        <RunButton
          busy={busy}
          disabled={!text.trim() || fileBusy}
          onClick={() => void run({ text })}
          idleLabel={t("tools.citation.runAll")}
          busyLabel={t("tools.citation.running")}
        />
      </div>

      <ToolError message={error} />

      {/* Nothing extracted is a normal outcome, not a failure — the document
          may simply have no reference list. The server's own English `detail`
          is deliberately not shown; this surface stays in one language. */}
      {result?.ok && result.detected === 0 && (
        <div className="rounded-xl border border-ink-200 bg-ink-50 p-4 text-[13px] text-ink-700">
          {t("tools.citation.errNoRefs")}
        </div>
      )}

      {items.length > 0 && (
        <div className="rounded-xl border border-ink-200 overflow-hidden">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 bg-ink-50 px-4 py-2.5 text-[12px] border-b border-ink-200">
            <span className="font-bold text-ink-900">
              {tn("tools.citation.summary_one", "tools.citation.summary_other", result!.checked)}
            </span>
            {confirmed > 0 && (
              <span className="text-[#3A5740]">
                {t("tools.citation.countConfirmed", { count: confirmed })}
              </span>
            )}
            {probable > 0 && (
              <span className="text-ink-600">
                {t("tools.citation.countProbable", { count: probable })}
              </span>
            )}
            {missing > 0 && (
              <span className="text-[#8E6B2A] font-semibold">
                {t("tools.citation.countMissing", { count: missing })}
              </span>
            )}
          </div>

          <ul className="m-0 p-0 list-none divide-y divide-ink-100">
            {items.map((item, i) => {
              const exact = item.found && item.matched_by === "doi";
              return (
                <li key={`${i}-${item.reference.slice(0, 40)}`} className="flex items-start gap-2.5 px-4 py-3">
                  {!item.ok ? (
                    <HelpCircle className="w-4 h-4 text-ink-400 shrink-0 mt-0.5" aria-hidden />
                  ) : !item.found ? (
                    <XCircle className="w-4 h-4 text-[#8E6B2A] shrink-0 mt-0.5" aria-hidden />
                  ) : exact ? (
                    <CheckCircle2 className="w-4 h-4 text-[#3A5740] shrink-0 mt-0.5" aria-hidden />
                  ) : (
                    <HelpCircle className="w-4 h-4 text-ink-500 shrink-0 mt-0.5" aria-hidden />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="text-[12.5px] font-semibold text-ink-900">
                      {!item.ok
                        ? t("tools.citation.itemUnchecked")
                        : !item.found
                          ? t("tools.citation.none")
                          : exact
                            ? t("tools.citation.exact")
                            : t("tools.citation.probable")}
                    </div>
                    {/* The student never typed these, so the line they came
                        from is what makes a verdict actionable. */}
                    <div className="mt-0.5 text-[12px] text-ink-600 leading-relaxed break-words">
                      {item.reference}
                    </div>
                    {item.found && (item.title || item.authors) && (
                      <div className="mt-1 text-[12px] text-ink-800">
                        {item.title && <span className="font-medium">{item.title}</span>}
                        {(item.authors || item.year) && (
                          <span className="text-ink-500">
                            {item.title ? " · " : ""}
                            {[item.authors, item.year].filter(Boolean).join(" · ")}
                          </span>
                        )}
                      </div>
                    )}
                    {item.doi && (
                      <a
                        href={`https://doi.org/${item.doi}`}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="inline-block mt-0.5 text-[11.5px] text-primary-600 underline"
                      >
                        doi.org/{item.doi}
                      </a>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>

          {result?.truncated && (
            <div className="px-4 py-2.5 bg-[#F5EFE2] text-[12px] text-[#6E5121] border-t border-[#E4D5B7]">
              {t("tools.citation.truncated", {
                checked: result.checked,
                detected: result.detected,
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
