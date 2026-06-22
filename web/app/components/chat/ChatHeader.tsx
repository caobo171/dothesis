import Link from "next/link";
import { ReactNode, useContext } from "react";
import { ArrowLeft, Bell, Download, History, Menu, PanelRight, PenSquare } from "lucide-react";

import { useMe } from "@/app/lib/use-me";
import { triggerExportDownload } from "@/app/lib/api";
import { ChatSidebarContext } from "./ChatShellLayout";
import { MODULES } from "./HomeDashboard";


// Header docx download button — enabled only when M5 has produced an
// export artifact (auto-fires when M5 flips to done; see
// api/app/agent_state.py:_auto_export_m5). The /exports/{filename} route
// 302s to a signed S3 URL; the browser can't attach a body to <a> download
// links, so instead of leaking the long-lived JWT in the URL we mint a
// short-lived, scoped stream token on click and navigate with ?st=.
function ExportDownloadButton({
  artifacts,
}: {
  artifacts?: { kind: string; download_url: string }[];
}) {
  const docx = artifacts?.find(a => a.kind === "docx") ?? artifacts?.[0];
  if (!docx) {
    return (
      <button
        type="button"
        title="Export — M5 not done yet"
        disabled
        className="w-8 h-8 rounded-full text-ink-300 inline-flex items-center justify-center cursor-not-allowed"
      >
        <Download className="w-4 h-4" />
      </button>
    );
  }
  return (
    <a
      href={docx.download_url}
      download
      onClick={(e) => { e.preventDefault(); void triggerExportDownload(docx.download_url); }}
      title="Download final thesis (DOCX)"
      className="w-8 h-8 rounded-full text-primary-600 hover:bg-primary-50 inline-flex items-center justify-center transition-colors"
    >
      <Download className="w-4 h-4" />
    </a>
  );
}


// Pill palette for the focus-bar status tag.
const STATUS_TAG: Record<string, { label: string; cls: string }> = {
  in_progress:  { label: "In progress",   cls: "bg-primary-50 text-primary-700" },
  needs_review: { label: "Needs review",  cls: "bg-amber-50 text-amber-700" },
  done:         { label: "Done",          cls: "bg-emerald-50 text-emerald-700" },
  locked:       { label: "Locked",        cls: "bg-ink-100 text-ink-500" },
};

// Sub-phase label per module (the "· Gap analysis" suffix in the design).
// Pulled from per-module skill conventions — only the modules with a
// well-defined sub-phase have one; others fall through silently.
const PHASE_LABEL: Record<string, string> = {
  M2: "Gap analysis",
  M3: "Measurement model",
  M4: "Analysis pipeline",
  M5: "Chapter sequence",
};


/**
 * Top focus bar — matches the design's FocusBar:
 *
 *     ← [M2] Literature Review · Gap analysis  [IN PROGRESS]   ⤴︎ ↓ 🔔 | JD [Jeendeet Lam / Pro Student]
 *
 * Left cluster: back-to-home circle, serif module chip, module label,
 * optional sub-phase label, status pill.
 * Right cluster: history button, export button, notifications bell with
 * red dot when unread, vertical divider, user avatar + name + tier.
 *
 * `autoDraftButton` is still a render-prop slot — ChatPane passes the
 * project-aware autodraft button in there.
 */
export function ChatHeader({
  projectName,
  threadName,
  autoDraftButton,
  projectId,
  hasChapters,
  focusModule,
  focusStatus,
  exportArtifacts,
}: {
  projectName: string;
  threadName: string;
  autoDraftButton: ReactNode;
  projectId?: string;
  hasChapters?: boolean;
  focusModule?: string;
  focusStatus?: string;
  /** M5 export artifacts (docx/pdf). When present, the Download button
   *  becomes a real link to the docx; otherwise it's disabled with a
   *  "no export yet" tooltip. */
  exportArtifacts?: { kind: string; download_url: string }[];
}) {
  const focusLabel = MODULES.find(m => m.id === focusModule)?.label;
  const phase = focusModule ? PHASE_LABEL[focusModule] : undefined;
  const tag = focusStatus ? STATUS_TAG[focusStatus] ?? STATUS_TAG.in_progress : null;
  const me = useMe();
  const sidebar = useContext(ChatSidebarContext);
  const user = me.data;
  const userInitials = user?.email
    ? user.email.slice(0, 2).toUpperCase()
    : "U";
  const userName = user?.username || user?.email?.split("@")[0] || "You";
  const userTier = user?.is_super_admin ? "Admin" : "Pro Student";

  return (
    <header
      className="sticky top-0 z-10 bg-white border-b border-ink-200 px-[22px] py-3 flex items-center gap-3"
      style={{ minHeight: 60 }}
    >
      {/* Open threads/workflow drawer — mobile only */}
      <button
        type="button"
        onClick={() => sidebar.open()}
        aria-label="Open menu"
        className="lg:hidden w-8 h-8 rounded-full bg-ink-100 text-ink-700 hover:bg-ink-200 inline-flex items-center justify-center shrink-0 transition-colors"
      >
        <Menu className="w-4 h-4" />
      </button>

      {/* Back to home */}
      <Link
        href="/"
        aria-label="Back to home"
        title="Back to home"
        className="w-8 h-8 rounded-full bg-ink-100 text-ink-700 hover:bg-ink-200 inline-flex items-center justify-center shrink-0 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
      </Link>

      {/* Focus cluster: chip + label + phase + status */}
      <div className="flex items-center gap-2.5 flex-1 min-w-0">
        {focusModule && (
          <span className="shrink-0 px-2.5 py-1 rounded-lg bg-primary-50 text-primary-700 font-serif font-extrabold text-[12.5px] tracking-[0.04em]">
            {focusModule}
          </span>
        )}
        <div className="flex items-baseline gap-2 min-w-0 whitespace-nowrap overflow-hidden">
          {focusLabel && (
            <span className="text-[15px] font-bold text-ink-900 truncate">{focusLabel}</span>
          )}
          {phase && (
            <span className="text-[12.5px] text-ink-500 shrink-0">· {phase}</span>
          )}
        </div>
        {tag && (
          <span
            className={`shrink-0 px-2.5 py-[3px] rounded-full text-[10.5px] font-bold uppercase tracking-[0.04em] whitespace-nowrap ${tag.cls}`}
          >
            {tag.label}
          </span>
        )}
        <span className="text-ink-300 shrink-0">·</span>
        <span className="text-[12.5px] text-ink-500 truncate" title={`${projectName} · ${threadName}`}>
          {projectName} · {threadName}
        </span>
      </div>

      {/* Right cluster */}
      <div className="flex items-center gap-1 shrink-0">
        {/* Open context panel drawer — mobile only */}
        <button
          type="button"
          onClick={() => sidebar.openContext()}
          aria-label="Open context panel"
          title="Context panel"
          className="lg:hidden w-8 h-8 rounded-full text-ink-500 hover:bg-ink-100 hover:text-ink-900 inline-flex items-center justify-center transition-colors"
        >
          <PanelRight className="w-4 h-4" />
        </button>

        {hasChapters && projectId && (
          <Link
            href={`/chat/projects/${projectId}/editor`}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 mr-1 text-[12.5px] font-semibold border-[1.5px] border-primary-600 text-primary-600 rounded-full hover:bg-primary-50 transition-colors"
          >
            <PenSquare className="w-3 h-3" /> Open editor
          </Link>
        )}

        {autoDraftButton}

        <button
          type="button"
          title="Version history"
          className="w-8 h-8 rounded-full text-ink-500 hover:bg-ink-100 hover:text-ink-900 inline-flex items-center justify-center transition-colors"
        >
          <History className="w-4 h-4" />
        </button>
        <ExportDownloadButton artifacts={exportArtifacts} />
        <button
          type="button"
          title="Notifications"
          className="relative w-8 h-8 rounded-full text-amber-700 bg-amber-50 hover:bg-amber-100 inline-flex items-center justify-center transition-colors"
        >
          <Bell className="w-4 h-4" />
          {/* Unread dot — TODO: hook to actual unread count when ready */}
          <span
            className="absolute top-1 right-1.5 w-2 h-2 rounded-full bg-red-500 border-[1.5px] border-white"
            aria-label="Unread notifications"
          />
        </button>

        <span className="w-px h-[22px] bg-ink-200 mx-1" />

        {/* User identity — solid ink avatar with serif-feel initials.
            The previous peach-pink gradient read as consumer-app brand; the
            academic palette uses a single dark surface. */}
        <div className="flex items-center gap-2 pl-1">
          <span
            className="w-[30px] h-[30px] rounded-full bg-ink-800 inline-flex items-center justify-center text-white font-bold text-[12px]"
            aria-hidden="true"
          >
            {userInitials}
          </span>
          <div className="leading-[1.15] whitespace-nowrap">
            <div className="text-[12.5px] font-semibold text-ink-900">{userName}</div>
            <div className="text-[10.5px] text-ink-500">{userTier}</div>
          </div>
        </div>
      </div>
    </header>
  );
}
