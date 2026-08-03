"use client";

import { ArrowUp, FileText, Paperclip, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useT } from "../../lib/i18n/LocaleProvider";
import type { AnalyzeKind } from "../../lib/bootstrap-payload";
import type { MessageKey } from "../../lib/i18n/messages/en";

/**
 * Chat-style composer for /new — one rounded box that is simultaneously the
 * text input, the attachment tray, and the drop target.
 *
 * Replaces a large dashed drop-zone with a collapsed "describe it instead"
 * link underneath. That older layout told students the primary move was to
 * upload, which is wrong for the ones who arrive with nothing but a topic —
 * exactly the students this product is most useful to. Typing is now the
 * headline action and attaching is the secondary one, so the page works whether
 * or not the student has files.
 *
 * Presentational by design: it owns no upload, analysis or navigation logic, so
 * it can be rendered in a test without mocking the API.
 */

export type StarterChip = {
  /** Chip label. */
  labelKey: MessageKey;
  /** Text written into the composer when the chip is clicked. */
  textKey: MessageKey;
  /**
   * What the first turn should DO. Omitted means the default assessment.
   *
   * The other chips are pure prefill — they describe a situation and the
   * bootstrap turn treats them all the same way. "Bài bị chê giống AI" is not
   * a situation, it's a different job, so this chip also selects the intent
   * the /new page hands to the chat surface.
   */
  kind?: AnalyzeKind;
};

export const STARTER_CHIPS: StarterChip[] = [
  { labelKey: "new.chip.draft", textKey: "new.chip.draft.text" },
  { labelKey: "new.chip.data", textKey: "new.chip.data.text" },
  { labelKey: "new.chip.papers", textKey: "new.chip.papers.text" },
  { labelKey: "new.chip.humanize", textKey: "new.chip.humanize.text", kind: "humanize" },
  { labelKey: "new.chip.fresh", textKey: "new.chip.fresh.text" },
];

export function ThesisComposer({
  value,
  onChange,
  files,
  onAddFiles,
  onRemoveFile,
  onSubmit,
  canSubmit,
  busy = false,
  accept,
  onKindChange,
}: {
  value: string;
  onChange: (next: string) => void;
  files: File[];
  /** Receives a SNAPSHOT array, never a live FileList — see the input's
   *  onChange for why that distinction matters. */
  onAddFiles: (files: File[] | FileList | null) => void;
  onRemoveFile: (index: number) => void;
  onSubmit: () => void;
  canSubmit: boolean;
  busy?: boolean;
  accept?: string;
  /** Fired when a chip selects a non-default first-turn intent. Optional so
   *  existing renders (and the component test) don't have to care. */
  onKindChange?: (kind: AnalyzeKind) => void;
}) {
  const t = useT();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);
  const [dragging, setDragging] = useState(false);

  // Grow with the content instead of scrolling inside a fixed box — a student
  // describing where they are writes 2-4 lines, and a 3-row box that scrolls
  // hides what they just typed.
  useEffect(() => {
    const el = textRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 260)}px`;
  }, [value]);

  const applyChip = (chip: StarterChip) => {
    onChange(t(chip.textKey));
    // Every chip reasserts the intent, including back to the default — clicking
    // "Mình có dữ liệu" after "Bài bị chê giống AI" must not leave the humanize
    // intent armed behind text that no longer asks for a rewrite.
    onKindChange?.(chip.kind ?? "assess");
    // Focus with the caret at the end: the chip is a STARTING point the student
    // is meant to edit, so land them ready to type rather than with the text
    // selected (which one keystroke would wipe).
    requestAnimationFrame(() => {
      const el = textRef.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(el.value.length, el.value.length);
    });
  };

  return (
    <div className="flex flex-col gap-3">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          onAddFiles(e.dataTransfer?.files ?? null);
        }}
        className={`rounded-2xl border bg-white shadow-sm transition-colors ${
          dragging ? "border-primary-500 ring-2 ring-primary-100" : "border-ink-200"
        }`}
      >
        {/* Attached files live INSIDE the box, above the text — they are part of
            the message being composed, not a separate list below it. */}
        {files.length > 0 && (
          <div className="flex flex-wrap gap-1.5 px-3 pt-3">
            {files.map((f, i) => (
              <span
                key={`${f.name}-${f.size}-${i}`}
                className="inline-flex items-center gap-1.5 rounded-lg bg-ink-50 border border-ink-200 pl-2 pr-1 py-1 text-[12px] max-w-[240px]"
              >
                <FileText className="w-3.5 h-3.5 text-ink-500 shrink-0" />
                <span className="truncate font-medium text-ink-800">{f.name}</span>
                <button
                  type="button"
                  onClick={() => onRemoveFile(i)}
                  disabled={busy}
                  aria-label={`${t("new.remove")} ${f.name}`}
                  className="w-4 h-4 rounded-full text-ink-400 hover:bg-ink-200 hover:text-ink-700 inline-flex items-center justify-center shrink-0 disabled:opacity-50"
                >
                  <X className="w-2.5 h-2.5" />
                </button>
              </span>
            ))}
          </div>
        )}

        <textarea
          ref={textRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            // Enter submits, Shift+Enter newlines — the convention every chat UI
            // shares, and this box looks exactly like one.
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (canSubmit) onSubmit();
            }
          }}
          disabled={busy}
          rows={2}
          placeholder={t("new.placeholder")}
          aria-label={t("new.title")}
          className="w-full resize-none bg-transparent px-4 pt-3.5 pb-1 text-[14px] leading-relaxed text-ink-900 placeholder:text-ink-400 focus:outline-none disabled:opacity-60"
        />

        <div className="flex items-center gap-2 px-3 pb-3 pt-1">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={busy}
            aria-label={t("new.attach")}
            title={t("new.attach")}
            className="w-8 h-8 rounded-lg text-ink-500 hover:bg-ink-100 hover:text-ink-900 inline-flex items-center justify-center disabled:opacity-50"
          >
            <Paperclip className="w-4 h-4" />
          </button>
          <span className="text-[11.5px] text-ink-400 truncate">
            {dragging ? t("new.dropHint") : t("new.fileTypes")}
          </span>
          <span className="flex-1" />
          <button
            type="button"
            onClick={onSubmit}
            disabled={!canSubmit}
            className="inline-flex items-center gap-1.5 rounded-xl bg-primary-600 px-3.5 py-2 text-[13px] font-bold text-white hover:bg-primary-700 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {busy ? t("new.analyzing") : t("new.analyze")}
            {!busy && <ArrowUp className="w-3.5 h-3.5" />}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={accept}
            onChange={(e) => {
              // Copy out of the live FileList BEFORE resetting the input:
              // clearing `value` empties `files` in place, so anything that
              // reads it later (a deferred setState updater, say) sees nothing.
              // The reset itself is required — without it, re-picking the same
              // filename fires no change event at all.
              const picked = Array.from(e.target.files ?? []);
              e.target.value = "";
              if (picked.length) onAddFiles(picked);
            }}
            className="hidden"
          />
        </div>
      </div>

      {/* Starter chips. They prefill EDITABLE text rather than submitting: an
          empty textarea gives a student no idea what a useful answer looks
          like, and that — not the styling — was the real failure of the old
          collapsed "describe it instead" link. */}
      <div className="flex flex-wrap gap-2">
        {STARTER_CHIPS.map((chip) => (
          <button
            key={chip.labelKey}
            type="button"
            onClick={() => applyChip(chip)}
            disabled={busy}
            className="rounded-full border border-ink-200 bg-white px-3 py-1.5 text-[12.5px] font-medium text-ink-700 hover:border-primary-400 hover:text-primary-700 hover:bg-primary-50/40 disabled:opacity-50"
          >
            {t(chip.labelKey)}
          </button>
        ))}
      </div>
    </div>
  );
}
