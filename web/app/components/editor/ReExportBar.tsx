"use client";

import Link from "next/link";
import { ArrowLeft, Download, Loader2, FileText } from "lucide-react";

import { triggerExportDownload } from "@/app/lib/api";
import { useT } from "@/app/lib/i18n/LocaleProvider";
import { useArtifactDownload } from "@/app/components/chat/hooks/useArtifactDownload";


/** What POST /m5/export hands back for each rendered file. */
export type ExportArtifact = {
  kind: string;
  download_url: string;
  size_bytes?: number | null;
};


type Props = {
  lastExportAt: Date | null;
  editsSinceExport: number;
  onReExport: () => Promise<void>;
  exporting: boolean;
  error?: Error | null;
  /** Where "back to chat" goes. The editor replaces the whole workspace, so
   *  without this there is no way out of it but the browser's back button. */
  projectId?: string;
  /** Files the last export produced. The endpoint has always returned
   *  {docx, pdf}; the editor threw the response away, so Re-export ran, said
   *  nothing, and left no file the student could reach. */
  artifacts?: ExportArtifact[];
  /** The document's Save. Slotted here rather than owned here so this bar stays
   *  about exporting — but it belongs in the one strip that is always on
   *  screen, not down the page next to whichever chapter you happen to be in. */
  save?: React.ReactNode;
  onBackToChat?: () => void;
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
  artifacts,
  onBackToChat,
}: Props) {
  const t = useT() as T;
  return (
    <header className="flex min-h-[64px] items-center gap-3 border-b border-ink-100 bg-white px-5 py-2.5 shadow-[0_1px_0_rgba(24,31,50,0.03)]">
      {/* The editor takes over the workspace — the chat, the context panel and
          the composer all go. Leaving without this meant the browser back
          button or retyping the URL. */}
      {projectId && (onBackToChat ? (
        <button
          type="button"
          onClick={onBackToChat}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-ink-200 px-2.5 py-1.5 text-[12.5px] font-semibold text-ink-700 hover:bg-ink-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden />
          {t("editor.backToChat")}
        </button>
      ) : (
        <Link
          href={`/chat/projects/${projectId}`}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-ink-200 px-2.5 py-1.5 text-[12.5px] font-semibold text-ink-700 hover:bg-ink-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden />
          {t("editor.backToChat")}
        </Link>
      ))}
      <span className="hidden h-8 w-px bg-ink-100 sm:block" aria-hidden />
      <div className="hidden min-w-0 items-center gap-2 md:flex">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-50 text-primary-700">
          <FileText className="h-4 w-4" aria-hidden />
        </span>
        <div className="min-w-0">
          <div className="truncate text-[13px] font-semibold text-ink-900">Thesis editor</div>
          <div className="text-[10px] text-ink-400">Academic writing workspace</div>
        </div>
      </div>
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
      {(artifacts ?? []).map(a => (
        <DownloadLink key={a.download_url} artifact={a} />
      ))}
      <button
        type="button"
        disabled={exporting}
        onClick={onReExport}
        className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:-translate-y-px hover:bg-primary-700 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {exporting ? t("editor.export.exporting") : t("editor.export.reExport")}
      </button>
    </header>
  );
}


/**
 * One produced file, as a download.
 *
 * Goes through the same mint-a-scoped-token path every other download button
 * uses: the /exports route 302s to a signed S3 URL but still needs auth, and a
 * browser cannot put a body on a navigation — so the long-lived JWT must never
 * end up in the URL.
 */
function DownloadLink({ artifact }: { artifact: ExportArtifact }) {
  const t = useT();
  const { busy, error, start } = useArtifactDownload();
  const label = (artifact.kind || "file").toUpperCase();

  return (
    <button
      type="button"
      onClick={() => { void start(() => triggerExportDownload(artifact.download_url)); }}
      disabled={busy}
      title={error || t("editor.export.download", { kind: label })}
      className={
        "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-[12px] font-semibold " +
        (error
          ? "border-[#E4C98A] bg-[#FBF3E0] text-[#6E5121]"
          : "border-ink-200 bg-white text-ink-700 hover:bg-ink-50")
      }
    >
      {busy
        ? <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
        : <Download className="h-3 w-3" aria-hidden />}
      {label}
    </button>
  );
}
