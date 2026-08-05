"use client";

import { useRef, useState } from "react";
import { FileText, Loader2, Download } from "lucide-react";

import { useT, useTn } from "@/app/lib/i18n/LocaleProvider";

import { scanDocument, humanizeDocument, type DocScan } from "./use-tool";
import { RunButton, ToolError, ToolCaveat } from "./shell";

/**
 * Whole-document rewrite: .docx in, .docx out, formatting intact.
 *
 * Separate from the passage box because the failure it fixes is structural.
 * Extracting a thesis to plain text drops heading levels and moves every table
 * to the end of the document, so what comes back is not something a student can
 * hand to a supervisor. This path never converts to text at all — it walks the
 * Word document and writes each rewrite back into the paragraph it came from.
 *
 * Two steps on purpose. The scan is free and tells you the size of the job
 * before any model runs, because a thesis is hundreds of paragraphs and one
 * click should not be able to spend an unknown number of someone's credits.
 */
export function HumanizeDocument() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [scan, setScan] = useState<DocScan | null>(null);
  const [busy, setBusy] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ filename: string; credits: number | null; rewritten: number | null } | null>(null);
  const t = useT();
  const tn = useTn();

  const pick = async (f: File | undefined | null) => {
    if (!f) return;
    setError(null);
    setScan(null);
    setDone(null);
    setFile(f);
    setBusy(true);
    try {
      setScan(await scanDocument(f, t));
    } catch (e) {
      setError((e as Error)?.message || t("tools.doc.readFailed"));
      setFile(null);
    } finally {
      setBusy(false);
    }
  };

  const run = async () => {
    if (!file) return;
    setRunning(true);
    setError(null);
    try {
      const r = await humanizeDocument(file, t);
      // Hand the file to the browser via an object URL. No navigation, so the
      // summary below stays on screen while the download saves.
      const url = URL.createObjectURL(r.blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = r.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setDone({ filename: r.filename, credits: r.credits, rewritten: r.rewritten });
    } catch (e) {
      setError((e as Error)?.message || t("tools.humanize.errFailed"));
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2 rounded-xl border border-dashed border-ink-200 bg-white px-3 py-2.5">
        <input
          ref={inputRef}
          type="file"
          accept=".docx"
          className="hidden"
          onChange={(e) => { void pick(e.target.files?.[0]); e.target.value = ""; }}
        />
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={busy || running}
          className="inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-primary-700 hover:text-primary-800 disabled:opacity-50"
        >
          {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden />
                : <FileText className="w-3.5 h-3.5" aria-hidden />}
          {busy ? t("tools.file.reading") : t("tools.doc.choose")}
        </button>
        <span className="text-[11.5px] text-ink-400 truncate min-w-0">
          {file ? file.name : t("tools.doc.wordOnly")}
        </span>
      </div>

      <ToolError message={error} />

      {scan?.ok && !done && (
        <div className="rounded-xl border border-ink-200 bg-ink-50 p-4">
          <div className="text-[13px] font-bold text-ink-900 mb-2">
            {tn("tools.doc.willRewrite_one", "tools.doc.willRewrite_other", scan.body_paragraphs)}
          </div>
          <ul className="m-0 p-0 list-none text-[12.5px] text-ink-600 space-y-1">
            <li>· {t("tools.doc.headings", { count: scan.headings })}</li>
            <li>· {t("tools.doc.tables", { count: scan.tables })}</li>
            <li>· {t("tools.doc.captions", { count: scan.short_or_captions })}</li>
          </ul>
          {/* The batch count was bolded via a nested <span>, which forced the
              sentence to be assembled in English word order. It is one string
              now so each locale can put the number where its grammar wants. */}
          <div className="mt-3 pt-3 border-t border-ink-200 text-[12.5px] text-ink-700">
            {tn("tools.doc.runsAs_one", "tools.doc.runsAs_other", scan.passages)}
          </div>
          <div className="mt-3.5">
            <RunButton
              busy={running}
              disabled={scan.body_paragraphs === 0}
              onClick={() => void run()}
              idleLabel={t("tools.doc.run")}
              busyLabel={t("tools.humanize.running")}
            />
          </div>
        </div>
      )}

      {scan?.ok && scan.body_paragraphs === 0 && (
        <ToolError message={t("tools.doc.errEmpty")} />
      )}

      {done && (
        <div className="rounded-xl border border-[#CFE0D2] bg-[#EEF4EE] p-4">
          <div className="flex items-center gap-2 text-[13.5px] font-bold text-[#3A5740]">
            <Download className="w-4 h-4" aria-hidden />
            {t("tools.doc.downloaded", { name: done.filename })}
          </div>
          {/* Built from whole translated clauses joined by " · ", not by
              concatenating an English fragment onto a number — the old version
              ended with a bare "." that belonged to the previous sentence. */}
          <div className="mt-1.5 text-[12.5px] text-[#3A5740]">
            {[
              done.rewritten !== null
                ? tn("tools.doc.rewritten_one", "tools.doc.rewritten_other", done.rewritten)
                : null,
              done.credits !== null && done.credits > 0
                ? t("tools.credits", { count: done.credits })
                : null,
            ]
              .filter(Boolean)
              .join(" · ")}
            {". "}
            {t("tools.doc.unchanged")}
          </div>
        </div>
      )}

      <ToolCaveat>
        {t("tools.doc.caveatBefore")}
        <em>{t("tools.doc.caveatEm")}</em>
        {t("tools.doc.caveatAfter")}
      </ToolCaveat>
    </div>
  );
}
