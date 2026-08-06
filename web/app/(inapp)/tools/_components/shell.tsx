"use client";

import { useRef, useState, type ReactNode } from "react";
import { Loader2, Paperclip } from "lucide-react";

import { useT } from "@/app/lib/i18n/LocaleProvider";

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
  hint,
}: {
  onText: (text: string) => void;
  busy: boolean;
  setBusy: (b: boolean) => void;
  onError: (msg: string | null) => void;
  /** Already-translated override. Defaults to the standard file-type list. */
  hint?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [filename, setFilename] = useState<string | null>(null);
  const t = useT();
  const hintText = hint ?? t("tools.file.types");

  const take = async (file: File | undefined | null) => {
    if (!file) return;
    onError(null);
    setBusy(true);
    setFilename(file.name);
    try {
      // extractFileText lives at module scope and so cannot call a hook — it
      // takes `t` instead, which keeps its thrown messages translated.
      const { extractFileText } = await import("./use-tool");
      onText(await extractFileText(file, t));
    } catch (e) {
      onError((e as Error)?.message || t("tools.file.readFailed"));
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
        {busy ? t("tools.file.reading") : t("tools.file.attach")}
      </button>
      <span className="text-[11.5px] text-ink-400 truncate min-w-0">
        {filename
          ? t("tools.file.loaded", { name: filename })
          : t("tools.file.orDrop", { hint: hintText })}
      </span>
    </div>
  );
}

/**
 * How far a document walk has got, while it is still walking.
 *
 * The spinner alone was the single worst thing about this screen: a 70-batch
 * thesis is minutes of a rotating circle with no way to tell a working run from
 * a dead one. The bar is driven by counts the server already records per batch,
 * so it reflects real work finishing rather than a timer pretending to.
 *
 * Renders nothing until the walk reports its first tick — a 0/0 bar would be a
 * worse lie than no bar.
 */
export function RunProgressBar({
  progress,
  label,
}: {
  progress: { done: number; total: number } | null;
  label: string;
}) {
  if (!progress || progress.total <= 0) return null;
  const pct = Math.min(100, Math.round((progress.done / progress.total) * 100));
  return (
    <div className="mt-3">
      <div className="mb-1.5 flex items-baseline justify-between text-[12px] text-ink-600">
        <span>{label}</span>
        <span className="tabular-nums text-ink-500">{pct}%</span>
      </div>
      <div
        className="h-1.5 w-full overflow-hidden rounded-full bg-ink-100"
        role="progressbar"
        aria-valuenow={progress.done}
        aria-valuemin={0}
        aria-valuemax={progress.total}
      >
        <div
          className="h-full rounded-full bg-primary-600 transition-[width] duration-500 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
