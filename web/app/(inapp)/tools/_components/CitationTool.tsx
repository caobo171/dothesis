"use client";

import { useState } from "react";
import { CheckCircle2, HelpCircle, XCircle } from "lucide-react";

import { useT } from "@/app/lib/i18n/LocaleProvider";

import { CitationList } from "./CitationList";
import { CiteDocument } from "./CiteDocument";
import { useTool } from "./use-tool";
import {
  ToolPanel, ToolTextarea, RunButton, ToolError, ToolCaveat,
} from "./shell";

type CitationOut = {
  ok: boolean;
  found: boolean;
  doi: string | null;
  title: string | null;
  authors: string | null;
  year: number | null;
  container: string | null;
  url: string | null;
  matched_by: string | null;
  warning: string | null;
  detail: string | null;
};

export function CitationTool() {
  // Three ways in, and the .docx one leads because it is the job students
  // actually arrive with — the finished thesis, wanting its citations sorted.
  //
  // History: this was one box that checked one reference, and students attached
  // whole theses to it. That could never work (the server caps the field at 2000
  // characters, and only the first 400 reach CrossRef anyway, so a chapter came
  // back "probably fine" against an unrelated paper). Documents now go to the
  // .docx mode, which resolves what is cited and cites what is not.
  const [mode, setMode] = useState<"docx" | "list" | "one">("docx");
  const [reference, setReference] = useState("");
  const { result, error, busy, run } = useTool<CitationOut>("/tools/verify-citation");
  const t = useT();

  // Three outcomes, not two. A DOI lookup is exact; a bibliographic search is
  // fuzzy — CrossRef returns its best match for ANY query, so a hit means
  // "something like this exists", not "this reference is real". Collapsing that
  // into a green tick is how a student keeps a fabricated source.
  const exact = result?.found && result.matched_by === "doi";

  return (
    <ToolPanel
      title={t("tools.citation.name")}
      blurb={t("tools.citation.blurb")}
    >
      <div className="flex flex-col gap-4">
        <div className="inline-flex self-start rounded-full border border-ink-200 p-0.5 bg-white">
          {(["docx", "list", "one"] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              aria-pressed={mode === m}
              className={`px-3.5 py-1.5 rounded-full text-[12.5px] font-semibold transition-colors ${
                mode === m ? "bg-primary-600 text-white" : "text-ink-600 hover:text-ink-900"
              }`}
            >
              {m === "docx"
                ? t("tools.citation.modeDocx")
                : m === "list"
                  ? t("tools.citation.modeList")
                  : t("tools.citation.modeOne")}
            </button>
          ))}
        </div>

        {mode === "docx" && <CiteDocument />}
        {mode === "list" && <CitationList />}

        {/* No attach control in single mode: a file is never one reference, and
            offering the button here is what sent whole theses at this box. */}
        {mode === "one" && (
        <ToolTextarea
          label={t("tools.citation.refLabel")}
          value={reference}
          onChange={setReference}
          rows={3}
          placeholder={t("tools.citation.placeholder")}
        />
        )}

        {mode === "one" && (
        <div>
          <RunButton
            busy={busy}
            disabled={reference.trim().length < 3}
            onClick={() => void run({ reference })}
            idleLabel={t("tools.citation.run")}
            busyLabel={t("tools.citation.running")}
          />
        </div>
        )}

        {mode === "one" && <ToolError message={error} />}

        {mode === "one" && result && !result.ok && (
          <ToolError message={result.detail || t("tools.citation.errUnreachable")} />
        )}

        {mode === "one" && result?.ok && (
          <div className="rounded-xl border border-ink-200 bg-ink-50 p-4">
            <div className="flex items-start gap-2.5">
              {!result.found ? (
                <XCircle className="w-5 h-5 text-[#8E6B2A] shrink-0 mt-px" aria-hidden />
              ) : exact ? (
                <CheckCircle2 className="w-5 h-5 text-[#3A5740] shrink-0 mt-px" aria-hidden />
              ) : (
                <HelpCircle className="w-5 h-5 text-ink-500 shrink-0 mt-px" aria-hidden />
              )}
              <div className="min-w-0">
                <div className="text-[14px] font-bold text-ink-900">
                  {!result.found
                    ? t("tools.citation.none")
                    : exact
                      ? t("tools.citation.exact")
                      : t("tools.citation.probable")}
                </div>
                {result.found && (
                  <div className="mt-1.5 text-[13px] text-ink-800 leading-relaxed">
                    {result.title && <div className="font-medium">{result.title}</div>}
                    <div className="text-ink-600 mt-0.5">
                      {[result.authors, result.year, result.container]
                        .filter(Boolean)
                        .join(" · ")}
                    </div>
                    {result.doi && (
                      <a
                        href={`https://doi.org/${result.doi}`}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="inline-block mt-1.5 text-[12.5px] text-primary-600 underline"
                      >
                        doi.org/{result.doi}
                      </a>
                    )}
                  </div>
                )}
                {result.warning && (
                  <p className="mt-2 mb-0 text-[12px] text-[#6E5121]">{result.warning}</p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* The .docx mode carries its own caveat (what it will and will not
            insert); this one is about CrossRef lookups, which is what the two
            checking modes do. */}
        {mode !== "docx" && <ToolCaveat>{t("tools.citation.caveat")}</ToolCaveat>}
      </div>
    </ToolPanel>
  );
}
