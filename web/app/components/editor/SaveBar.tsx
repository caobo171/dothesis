"use client";

import { AlertTriangle, Check, Loader2, Save } from "lucide-react";

import { useT } from "@/app/lib/i18n/LocaleProvider";

/**
 * Whether this chapter has unsaved changes, and the button that saves it.
 *
 * The editor used to PATCH on a 1s debounce after every keystroke — a write per
 * sentence, per student, for as long as the tab was open. It now records that
 * something changed and asks for the save, which is also clearer: a student can
 * see whether their work is stored instead of trusting that it is.
 *
 * The unsaved state is the one worth being loud about, because it is the one
 * where closing the tab costs them the work.
 */
export function SaveBar({
  dirty, saving, lastSavedAt, error, onSave,
}: {
  dirty: boolean;
  saving: boolean;
  lastSavedAt: Date | null;
  error: Error | null;
  onSave: () => void;
}) {
  const t = useT();

  return (
    <div className="mb-2 flex items-center gap-2 text-[11.5px]" data-testid="save-bar">
      <span className="flex items-center gap-1.5" aria-live="polite">
        {saving ? (
          <>
            <Loader2 className="h-3 w-3 animate-spin text-ink-400" aria-hidden />
            <span className="text-ink-400">{t("editor.save.saving")}</span>
          </>
        ) : dirty ? (
          <>
            <span className="h-1.5 w-1.5 rounded-full bg-[#C9962F]" aria-hidden />
            <span className="text-[#6E5121] font-medium">{t("editor.save.unsaved")}</span>
          </>
        ) : lastSavedAt ? (
          <>
            <Check className="h-3 w-3 text-ink-400" aria-hidden />
            <span className="text-ink-400">
              {t("editor.save.savedAt", {
                time: lastSavedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
              })}
            </span>
          </>
        ) : (
          <span className="text-ink-400">{t("editor.save.clean")}</span>
        )}
      </span>

      {/* Only when there is something to save — a permanently enabled Save
          teaches nothing about whether the work is stored. */}
      {(dirty || error) && (
        <button
          type="button"
          onClick={onSave}
          disabled={saving}
          className="inline-flex items-center gap-1.5 rounded-md border border-primary-200 bg-primary-50 px-2.5 py-1 font-semibold text-primary-700 hover:bg-primary-100 disabled:opacity-50"
        >
          <Save className="h-3 w-3" aria-hidden />
          {t("editor.save.action")}
        </button>
      )}

      {error && (
        <span role="alert" className="flex items-center gap-1.5 text-[#6E5121]">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden />
          {t("editor.save.failed")}
        </span>
      )}
    </div>
  );
}
