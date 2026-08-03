"use client";

import { useRef, useState } from "react";
import { FileText, Loader2, Download } from "lucide-react";

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

  const pick = async (f: File | undefined | null) => {
    if (!f) return;
    setError(null);
    setScan(null);
    setDone(null);
    setFile(f);
    setBusy(true);
    try {
      setScan(await scanDocument(f));
    } catch (e) {
      setError((e as Error)?.message || "Could not read that document.");
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
      const r = await humanizeDocument(file);
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
      setError((e as Error)?.message || "The rewrite did not complete.");
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
          {busy ? "Reading…" : "Choose a .docx"}
        </button>
        <span className="text-[11.5px] text-ink-400 truncate min-w-0">
          {file ? file.name : "Word only — a PDF has no editable paragraphs"}
        </span>
      </div>

      <ToolError message={error} />

      {scan?.ok && !done && (
        <div className="rounded-xl border border-ink-200 bg-ink-50 p-4">
          <div className="text-[13px] font-bold text-ink-900 mb-2">
            {scan.body_paragraphs} paragraphs will be rewritten
          </div>
          <ul className="m-0 p-0 list-none text-[12.5px] text-ink-600 space-y-1">
            <li>· {scan.headings} headings left untouched — they're structure, not prose</li>
            <li>· {scan.tables} tables left untouched — they're data</li>
            <li>· {scan.short_or_captions} captions and short lines skipped</li>
          </ul>
          <div className="mt-3 pt-3 border-t border-ink-200 text-[12.5px] text-ink-700">
            Runs as <span className="font-semibold">{scan.passages}</span>{" "}
            {scan.passages === 1 ? "rewrite" : "rewrites"} (paragraphs are batched
            by section). You're charged for the tokens actually used — the exact
            amount lands in Transactions.
          </div>
          <div className="mt-3.5">
            <RunButton
              busy={running}
              disabled={scan.body_paragraphs === 0}
              onClick={() => void run()}
              idleLabel="Humanize document"
              busyLabel="Rewriting…"
            />
          </div>
        </div>
      )}

      {scan?.ok && scan.body_paragraphs === 0 && (
        <ToolError message="Nothing to rewrite — this document is headings, tables and captions only." />
      )}

      {done && (
        <div className="rounded-xl border border-[#CFE0D2] bg-[#EEF4EE] p-4">
          <div className="flex items-center gap-2 text-[13.5px] font-bold text-[#3A5740]">
            <Download className="w-4 h-4" aria-hidden />
            {done.filename} downloaded
          </div>
          <div className="mt-1.5 text-[12.5px] text-[#3A5740]">
            {done.rewritten !== null && `${done.rewritten} paragraphs rewritten`}
            {done.credits !== null && done.credits > 0 && ` · ${done.credits} credits`}
            . Headings, tables and numbering are unchanged.
          </div>
        </div>
      )}

      <ToolCaveat>
        Tables and headings are never rewritten, and any batch whose rewrite would
        have altered a number or citation keeps its original text. One real loss:
        bold or italic <em>inside</em> a sentence isn't preserved — paragraph
        styles, heading levels, tables and numbering are.
      </ToolCaveat>
    </div>
  );
}
