"use client";

import { useMemo } from "react";
import { diff_match_patch } from "diff-match-patch";
import { X } from "lucide-react";

import { useT } from "@/app/lib/i18n/LocaleProvider";

export type ChapterChange = { chapter: string; before: string; after: string };

/**
 * What "Unsaved changes" actually means, for this document.
 *
 * The bar could only say that SOMETHING had changed. After an hour of editing
 * across five chapters that is not enough to decide whether to save — and it is
 * the same information a student already had from the fact that they were
 * typing. This shows the text itself, per chapter, with the additions and
 * deletions marked.
 *
 * diff_cleanupSemantic is what makes it readable: the raw character diff of a
 * reworded sentence is a confetti of one-letter runs, and it coalesces those
 * into the word- and phrase-level edits a person actually made.
 */
export function UnsavedDiff({
  changes, onClose, onSave,
}: {
  changes: ChapterChange[];
  onClose: () => void;
  onSave: () => void;
}) {
  const t = useT();
  const dmp = useMemo(() => new diff_match_patch(), []);

  const diffs = useMemo(
    () => changes.map(c => {
      const parts = dmp.diff_main(c.before, c.after);
      dmp.diff_cleanupSemantic(parts);
      // An unchanged run between two edits is context; a long one is the rest
      // of the chapter and would bury them.
      return { chapter: c.chapter, parts };
    }),
    [changes, dmp],
  );

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/30 p-6"
      role="dialog"
      aria-modal="true"
      aria-label={t("editor.diff.title")}
      onClick={onClose}
    >
      <div
        className="flex max-h-full w-full max-w-3xl flex-col rounded-2xl bg-white shadow-xl"
        onClick={e => e.stopPropagation()}
      >
        <header className="flex items-center gap-3 border-b border-ink-200 px-5 py-3">
          <div>
            <div className="text-sm font-semibold text-ink-900">{t("editor.diff.title")}</div>
            <div className="text-[11.5px] text-ink-400">{t("editor.diff.legend")}</div>
          </div>
          <span className="flex-1" />
          <button
            type="button"
            onClick={() => { onSave(); onClose(); }}
            className="rounded-md border border-primary-200 bg-primary-50 px-3 py-1.5 text-[12.5px] font-semibold text-primary-700 hover:bg-primary-100"
          >
            {t("editor.save.action")}
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("editor.diff.close")}
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-ink-500 hover:bg-ink-100"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4 space-y-5">
          {diffs.length === 0 && (
            <p className="text-[13px] text-ink-500">{t("editor.diff.none")}</p>
          )}
          {diffs.map(({ chapter, parts }) => (
            <section key={chapter} data-testid={`diff-${chapter}`}>
              <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-400">
                {chapter}
              </h3>
              <p className="whitespace-pre-wrap break-words font-serif text-[13.5px] leading-relaxed text-ink-800">
                {parts.map(([op, text], i) =>
                  op === 1 ? (
                    <ins key={i} className="bg-[#E3F1E6] text-[#2F5D3A] no-underline">{text}</ins>
                  ) : op === -1 ? (
                    <del key={i} className="bg-[#FBE4E4] text-[#8B3A3A]">{text}</del>
                  ) : (
                    <span key={i} className="text-ink-400">{text}</span>
                  ),
                )}
              </p>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
