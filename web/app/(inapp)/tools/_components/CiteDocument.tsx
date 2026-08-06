"use client";

import { useRef, useState } from "react";
import { FileText, Loader2, Download } from "lucide-react";

import { useT, useTn } from "@/app/lib/i18n/LocaleProvider";

import { scanCiteDocument, citeDocument, type CiteScan, useRunProgress } from "./use-tool";
import { RunButton, ToolError, ToolCaveat, RunProgressBar } from "./shell";

/**
 * Whole-document citing: .docx in, .docx out, formatting intact.
 *
 * Deliberately the same two-step shape as HumanizeDocument — scan first, then
 * run — because the second phase spends credits per claim and "upload and hope"
 * is not a defensible way to bill someone. The scan itself is free.
 */
export function CiteDocument() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [scan, setScan] = useState<CiteScan | null>(null);
  // Phase B is opt-in. Phase A (resolving what is already cited) calls no model
  // and cannot invent anything, so a student who only wants their reference
  // list fixed should not be pushed through the half that costs credits.
  const [addMissing, setAddMissing] = useState(true);
  const [busy, setBusy] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{
    filename: string; credits: number | null; resolved: number | null;
    unresolved: number | null; weak: number | null; uncited: number | null;
    added: number | null; marked: number | null; linked: number | null;
  } | null>(null);
  const t = useT();
  const tn = useTn();
  // Same live counter as the humanize screen: phase A is a lookup per
  // source and phase B a model call per batch, so this is minutes of
  // waiting that used to show nothing but a spinning circle.
  const progress = useRunProgress(running);

  const pick = async (f: File | undefined | null) => {
    if (!f) return;
    setError(null);
    setScan(null);
    setDone(null);
    setFile(f);
    setBusy(true);
    try {
      setScan(await scanCiteDocument(f, t));
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
      // Batch count from the free scan sets the request deadline — see
      // docTimeoutMs. Without one this spinner can outlive its own connection.
      const r = await citeDocument(file, addMissing, t, scan?.passages);
      const url = URL.createObjectURL(r.blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = r.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setDone({
        filename: r.filename, credits: r.credits, resolved: r.resolved,
        unresolved: r.unresolved, weak: r.weak, uncited: r.uncited,
        added: r.added, marked: r.marked, linked: r.linked,
      });
    } catch (e) {
      setError((e as Error)?.message || t("tools.cite.errFailed"));
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
            {tn("tools.cite.found_one", "tools.cite.found_other", scan.distinct_sources)}
          </div>
          <ul className="m-0 p-0 list-none text-[12.5px] text-ink-600 space-y-1">
            <li>· {t("tools.cite.willResolve")}</li>
            <li>· {t("tools.cite.willLink")}</li>
            <li>
              · {scan.has_reference_section
                  ? t("tools.cite.willReplaceList", { count: scan.existing_references })
                  : t("tools.cite.willCreateList")}
            </li>
            <li>· {t("tools.cite.willKeepFormat", { count: scan.headings })}</li>
            {/* The price, quoted before it is spent. Phase A is billed per
                source looked up, so the scan can name the exact number; phase B
                is billed on tokens and cannot be quoted from a scan. */}
            <li className="font-semibold text-ink-800">
              · {t("tools.cite.willCost", { count: scan.resolve_cost })}
            </li>
          </ul>

          <label className="mt-3 pt-3 border-t border-ink-200 flex items-start gap-2.5 cursor-pointer">
            <input
              type="checkbox"
              checked={addMissing}
              onChange={(e) => setAddMissing(e.target.checked)}
              className="mt-0.5"
            />
            <span className="text-[12.5px] text-ink-700 leading-relaxed">
              <span className="font-semibold">{t("tools.cite.addMissing")}</span>
              <br />
              {t("tools.cite.addMissingHint", { count: scan.body_paragraphs })}
            </span>
          </label>

          <div className="mt-3.5">
            <RunButton
              busy={running}
              disabled={false}
              onClick={() => void run()}
              idleLabel={t("tools.cite.run")}
              busyLabel={
                progress
                  ? t("tools.doc.runningCount", {
                      done: progress.done, total: progress.total })
                  : t("tools.cite.running")
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
            {done.resolved !== null && (
              <li>· {t("tools.cite.doneResolved", { count: done.resolved })}</li>
            )}
            {done.unresolved !== null && done.unresolved > 0 && (
              <li>· {t("tools.cite.doneUnresolved", { count: done.unresolved })}</li>
            )}
            {done.weak !== null && done.weak > 0 && (
              <li>· {t("tools.cite.doneWeak", { count: done.weak })}</li>
            )}
            {done.uncited !== null && done.uncited > 0 && (
              <li>· {t("tools.cite.doneUncited", { count: done.uncited })}</li>
            )}
            {done.added !== null && done.added > 0 && (
              <li>· {t("tools.cite.doneAdded", { count: done.added })}</li>
            )}
            {done.marked !== null && done.marked > 0 && (
              <li>· {t("tools.cite.doneMarked", { count: done.marked })}</li>
            )}
            {done.linked !== null && done.linked > 0 && (
              <li>· {t("tools.cite.doneLinked", { count: done.linked })}</li>
            )}
            {done.credits !== null && done.credits > 0 && (
              <li>· {t("tools.credits", { count: done.credits })}</li>
            )}
          </ul>
        </div>
      )}

      <ToolCaveat>{t("tools.cite.caveat")}</ToolCaveat>
    </div>
  );
}
