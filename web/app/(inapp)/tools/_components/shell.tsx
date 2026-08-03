"use client";

import { useRef, useState, type ReactNode } from "react";
import { Loader2, Paperclip } from "lucide-react";

/** Shared chrome for a tool panel: title, one-line purpose, body, action row. */
export function ToolPanel({
  title,
  blurb,
  children,
}: {
  title: string;
  blurb: string;
  children: ReactNode;
}) {
  return (
    <section className="bg-white border border-ink-200 rounded-2xl p-5">
      <h2 className="m-0 text-[17px] font-extrabold tracking-tight text-ink-900">{title}</h2>
      <p className="mt-1 mb-4 text-[13px] text-ink-500 leading-relaxed max-w-2xl">{blurb}</p>
      {children}
    </section>
  );
}

export function ToolTextarea({
  value,
  onChange,
  placeholder,
  rows = 8,
  label,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  rows?: number;
  label?: string;
}) {
  return (
    <label className="block">
      {label && (
        <span className="block text-[12px] font-semibold text-ink-700 mb-1.5">{label}</span>
      )}
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={rows}
        className="w-full rounded-xl border border-ink-200 px-3.5 py-3 text-[14px] leading-relaxed text-ink-900 placeholder:text-ink-400 focus:border-primary-400 focus:outline-none resize-y"
      />
    </label>
  );
}

export function RunButton({
  busy,
  disabled,
  onClick,
  idleLabel,
  busyLabel,
}: {
  busy: boolean;
  disabled: boolean;
  onClick: () => void;
  idleLabel: string;
  busyLabel: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || busy}
      className="inline-flex items-center gap-2 bg-primary-600 text-white px-5 py-2.5 rounded-full text-[13.5px] font-semibold hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
    >
      {busy && <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden />}
      {busy ? busyLabel : idleLabel}
    </button>
  );
}

/** Failure line. role="alert" so it is announced, not just drawn. */
export function ToolError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div
      role="alert"
      className="mt-3 rounded-xl border border-[#E4D5B7] bg-[#F5EFE2] px-3.5 py-2.5 text-[12.5px] text-[#6E5121]"
    >
      {message}
    </div>
  );
}

/**
 * A claim the tool is NOT making.
 *
 * Load-bearing rather than decorative: writing-rhythm measures sentence-length
 * variance and cannot see perplexity, so a student reading its number as a
 * Turnitin prediction has been misled by us — and they find out at submission.
 * The endpoint's own description says so; the UI has to say it too.
 */
export function ToolCaveat({ children }: { children: ReactNode }) {
  return (
    <p className="mt-3 text-[11.5px] text-ink-500 leading-relaxed border-l-2 border-ink-200 pl-3">
      {children}
    </p>
  );
}

/**
 * Attach-a-file control that fills a textarea instead of replacing it.
 *
 * Extraction resolves to plain text and drops it straight into the box the
 * student can still edit. That matters for these tools specifically: a thesis
 * PDF extracts to tens of pages, and humanize/rhythm both want ONE passage —
 * so the extracted text has to stay editable for them to cut it down. A
 * hidden "file attached" chip would give them no way to do that.
 */
export function FileDrop({
  onText,
  busy,
  setBusy,
  onError,
  hint = "PDF, Word or text",
}: {
  onText: (text: string) => void;
  busy: boolean;
  setBusy: (b: boolean) => void;
  onError: (msg: string | null) => void;
  hint?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [filename, setFilename] = useState<string | null>(null);

  const take = async (file: File | undefined | null) => {
    if (!file) return;
    onError(null);
    setBusy(true);
    setFilename(file.name);
    try {
      const { extractFileText } = await import("./use-tool");
      onText(await extractFileText(file));
    } catch (e) {
      onError((e as Error)?.message || "Could not read that file.");
      setFilename(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        void take(e.dataTransfer.files?.[0]);
      }}
      className={`flex items-center gap-2 rounded-xl border border-dashed px-3 py-2 transition-colors ${
        dragging ? "border-primary-400 bg-primary-50" : "border-ink-200 bg-white"
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx,.txt,.md,.markdown"
        className="hidden"
        onChange={(e) => {
          void take(e.target.files?.[0]);
          e.target.value = "";  // let the same file be re-picked after an edit
        }}
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={busy}
        className="inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-primary-700 hover:text-primary-800 disabled:opacity-50"
      >
        {busy ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden />
        ) : (
          <Paperclip className="w-3.5 h-3.5" aria-hidden />
        )}
        {busy ? "Reading…" : "Attach a file"}
      </button>
      <span className="text-[11.5px] text-ink-400 truncate min-w-0">
        {filename ? `${filename} — text loaded below, edit it freely` : `${hint} · or drop one here`}
      </span>
    </div>
  );
}
