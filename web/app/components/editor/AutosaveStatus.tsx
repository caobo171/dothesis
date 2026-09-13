"use client";

import { AlertTriangle, Check, Loader2 } from "lucide-react";

import { useT } from "@/app/lib/i18n/LocaleProvider";

/**
 * What happened to the last autosave.
 *
 * The editor has no Save button on purpose — every keystroke is debounced into
 * a PATCH. But nothing on screen said that, and, worse, nothing said when a
 * save had FAILED: `useChapterAutosave` gives up after three attempts and sets
 * an `error` that no component read. A student typing through an expired
 * session saw an ordinary editor the entire time.
 *
 * So: quiet on success (a timestamp, not a badge), and on failure a persistent
 * warning with a retry — because that is the state where doing nothing costs
 * them the work.
 */
export function AutosaveStatus({
  saving, lastSavedAt, error, onRetry,
}: {
  saving: boolean;
  lastSavedAt: Date | null;
  error: Error | null;
  onRetry: () => void;
}) {
  const t = useT();

  if (error) {
    return (
      <div
        role="alert"
        data-testid="autosave-error"
        className="mb-3 flex items-center gap-2 rounded-lg border border-[#E4C98A] bg-[#FBF3E0] px-3 py-2 text-[12.5px] text-[#6E5121]"
      >
        <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden />
        <span className="flex-1">{t("editor.autosave.failed")}</span>
        <button
          type="button"
          onClick={onRetry}
          className="shrink-0 rounded-md border border-[#E4C98A] bg-white px-2 py-1 font-semibold hover:bg-[#FBF3E0] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
        >
          {t("editor.autosave.retry")}
        </button>
      </div>
    );
  }

  return (
    <div
      className="mb-2 flex items-center gap-1.5 text-[11.5px] text-ink-400"
      aria-live="polite"
      data-testid="autosave-status"
    >
      {saving ? (
        <>
          <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
          {t("editor.autosave.saving")}
        </>
      ) : lastSavedAt ? (
        <>
          <Check className="h-3 w-3" aria-hidden />
          {t("editor.autosave.savedAt", {
            time: lastSavedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          })}
        </>
      ) : (
        t("editor.autosave.idle")
      )}
    </div>
  );
}
