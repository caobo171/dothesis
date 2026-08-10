"use client";

import { useRef, useState } from "react";
import { FileText, Loader2, Download, ShieldAlert } from "lucide-react";

import { useT } from "@/app/lib/i18n/LocaleProvider";

import {
  scanSimilarityDocument, similarityDocument, useRunProgress, useSavedFile,
  type SimilarityScan,
} from "./use-tool";
import { RunButton, ToolError, ToolCaveat, RunProgressBar } from "./shell";

/**
 * Whole-document similarity & citation self-check.
 *
 * Same two-step shape as CiteDocument and HumanizeDocument — free scan, then a
 * billed run — for the same reason: a student should see the job before paying.
 *
 * What is different is the failure mode. The other tools can only
 * under-deliver; this one can be MISREAD, and the misreading — "it found
 * nothing, so I'm clean" — is the expensive kind. So what was and was not
 * searched is stated before the run, again beside the result counts, and a
 * third time on the summary page inside the returned document.
 */
export function SimilarityDocument() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [scan, setScan] = useState<SimilarityScan | null>(null);
  const [busy, setBusy] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{
    filename: string; credits: number | null; corpusChecked: boolean;
    flagged: number | null; duplication: number | null;
    uncitedQuotes: number | null; citationGaps: number | null;
  } | null>(null);
  const t = useT();
  const progress = useRunProgress(running);

  // Keeps the finished file downloadable instead of revoking it one line
  // after the auto-click. See useSavedFile.
  const { saved, save, clearSaved } = useSavedFile();

  const pick = async (f: File | undefined | null) => {
    if (!f) return;
    setError(null);
    setScan(null);
    setDone(null);
    clearSaved();
    setFile(f);
    setBusy(true);
    try {
      setScan(await scanSimilarityDocument(f, t));
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
      const r = await similarityDocument(file, t);
      save(r.blob, r.filename);
      setDone(r);
    } catch (e) {
      setError((e as Error)?.message || t("tools.sim.errFailed"));
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-2 py-2">
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
            {t("tools.sim.willCheck", { count: scan.body_paragraphs })}
          </div>
          <ul className="m-0 p-0 list-none text-[12.5px] text-ink-600 space-y-1">
            <li>· {t("tools.sim.willDuplication")}</li>
            <li>· {t("tools.sim.willQuotes", { count: scan.quotations })}</li>
            <li>· {t("tools.sim.willReferences", { count: scan.reference_entries })}</li>
            {/* Stated where the student is deciding to spend, not only after. */}
            <li className={scan.corpus_available ? "" : "font-semibold text-ink-800"}>
              · {scan.corpus_available
                  ? t("tools.sim.willCorpus")
                  : t("tools.sim.willNotCorpus")}
            </li>
            <li className="font-semibold text-ink-800">
              · {t("tools.sim.willCost", { count: scan.check_cost })}
            </li>
          </ul>

          <div className="mt-3.5">
            <RunButton
              busy={running}
              disabled={false}
              onClick={() => void run()}
              idleLabel={t("tools.sim.run")}
              busyLabel={
                progress
                  ? t("tools.doc.runningCount", {
                      done: progress.done, total: progress.total })
                  : t("tools.sim.running")
              }
            />
            <RunProgressBar
              progress={progress}
              label={t("tools.doc.runningSteps", {
                done: progress?.done ?? 0, total: progress?.total ?? 0 })}
            />
          </div>
        </div>
      )}

      {done && (
        <div className="rounded-xl border border-[#CFE0D2] bg-[#EEF4EE] p-4">
          <div className="flex items-center gap-2 text-[13.5px] font-bold text-[#3A5740]">
            <Download className="w-4 h-4" aria-hidden />
            {t("tools.doc.downloaded", { name: done.filename })}
          </div>
          <ul className="mt-1.5 mb-0 p-0 list-none text-[12.5px] text-[#3A5740] space-y-0.5">
            <li>· {t("tools.sim.doneFlagged", { count: done.flagged ?? 0 })}</li>
            <li>· {t("tools.sim.doneDuplication", { count: done.duplication ?? 0 })}</li>
            <li>· {t("tools.sim.doneQuotes", { count: done.uncitedQuotes ?? 0 })}</li>
            <li>· {t("tools.sim.doneGaps", { count: done.citationGaps ?? 0 })}</li>
            {done.credits !== null && done.credits > 0 && (
              <li>· {t("tools.credits", { count: done.credits })}</li>
            )}
          </ul>
          {/* Beside the numbers, not only in the small print. A student reading
              "0 flagged" without this reads it as "0% similarity". */}
          {!done.corpusChecked && (
            <p className="mt-2.5 pt-2.5 border-t border-[#CFE0D2] inline-flex items-start gap-1.5 text-[11.5px] text-[#6E5121]">
              <ShieldAlert className="mt-0.5 w-3.5 h-3.5 shrink-0" aria-hidden />
              {t("tools.sim.resultNoCorpus")}
            </p>
          )}
          {/* The actual way to get the file. The line above says a download
              HAPPENED; when the browser blocked it or the student missed it,
              this is the only thing between them and paying twice. */}
          {saved && (
            <a
              href={saved.url}
              download={saved.name}
              className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-[#3A5740] px-3 py-1.5 text-[12.5px] font-semibold text-white hover:opacity-90"
            >
              <Download className="w-3.5 h-3.5" aria-hidden />
              {t("tools.doc.downloadAgain")}
            </a>
          )}
        </div>
      )}

      <ToolCaveat>
        {scan?.corpus_available ? t("tools.sim.caveatCorpus") : t("tools.sim.caveat")}
      </ToolCaveat>
    </div>
  );
}
