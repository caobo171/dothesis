"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { useT } from "@/app/lib/i18n/LocaleProvider";


type Props = {
  lastExportAt: Date | null;
  editsSinceExport: number;
  onReExport: () => Promise<void>;
  exporting: boolean;
  error?: Error | null;
  /** Where "back to chat" goes. The editor replaces the whole workspace, so
   *  without this there is no way out of it but the browser's back button. */
  projectId?: string;
  /** The document's Save. Slotted here rather than owned here so this bar stays
   *  about exporting — but it belongs in the one strip that is always on
   *  screen, not down the page next to whichever chapter you happen to be in. */
  save?: React.ReactNode;
};


type T = (key: string, params?: Record<string, string | number>) => string;

function _formatRelative(t: Date | null, tr: T): string {
  if (!t) return tr("editor.export.never");
  const diff = Date.now() - t.getTime();
  const m = Math.round(diff / 60_000);
  if (m < 1) return tr("editor.export.justNow");
  if (m < 60) return tr("editor.export.minutesAgo", { count: m });
  return tr("editor.export.hoursAgo", { count: Math.round(m / 60) });
}


// Pinned at the top of the editor surface. Always visible.
// Freshness counter (editsSinceExport) is driven by parent watching useChapterSave.
export function ReExportBar({
  lastExportAt, editsSinceExport, onReExport, exporting, error, projectId, save,
}: Props) {
  const t = useT() as T;
  return (
    <div className="flex items-center gap-3 border-b border-gray-200 px-6 py-3 bg-white">
      {/* The editor takes over the workspace — the chat, the context panel and
          the composer all go. Leaving without this meant the browser back
          button or retyping the URL. */}
      {projectId && (
        <Link
          href={`/chat/projects/${projectId}`}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-ink-200 px-2.5 py-1.5 text-[12.5px] font-semibold text-ink-700 hover:bg-ink-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden />
          {t("editor.backToChat")}
        </Link>
      )}
      <div className="text-sm">
        <span className="text-gray-500">{t("editor.export.last")} </span>
        <span className="font-medium text-gray-900">{_formatRelative(lastExportAt, t)}</span>
        {editsSinceExport > 0 && (
          <span className="text-gray-500 ml-2">
            · {t("editor.export.editsSince", { count: editsSinceExport })}
          </span>
        )}
        {error && (
          <span className="ml-3 text-red-600 text-xs">
            {t("editor.export.failed", { message: error.message })}
          </span>
        )}
      </div>
      <span className="flex-1" />
      {/* Save sits left of Re-export: you save, then you export. */}
      {save}
      <button
        type="button"
        disabled={exporting}
        onClick={onReExport}
        className="text-sm px-4 py-1.5 bg-primary-600 text-white rounded-md font-medium hover:bg-primary-700 disabled:opacity-60 disabled:cursor-not-allowed"
      >
        {exporting ? t("editor.export.exporting") : t("editor.export.reExport")}
      </button>
    </div>
  );
}
