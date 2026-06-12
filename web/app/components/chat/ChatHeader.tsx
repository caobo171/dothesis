import Link from "next/link";
import { ReactNode } from "react";
import { ArrowLeft, PenSquare } from "lucide-react";

import { MODULES } from "./HomeDashboard";


// Focus-bar status tag palettes (DoThesis.html design: tag.in_progress
// primary, tag.needs_review amber, tag.done green, tag.locked muted).
const STATUS_TAG: Record<string, { label: string; cls: string }> = {
  in_progress:  { label: "In progress",  cls: "bg-primary-50 text-primary-700" },
  needs_review: { label: "⚠ Needs review", cls: "bg-[var(--pause-bg)] text-[var(--pause-fg)]" },
  done:         { label: "Done",         cls: "bg-[var(--ok-bg)] text-[var(--ok-fg)]" },
  locked:       { label: "Locked",       cls: "bg-ink-100 text-ink-500" },
};


// 2026-06-10 — restyled to the DoThesis.html focus bar: back-to-home icon,
// serif module chip + module label + status tag, project/thread breadcrumb,
// pill actions. Same required props as before so ChatPane and tests don't
// change shape; focusModule/focusStatus are additive.
export function ChatHeader({
  projectName,
  threadName,
  autoDraftButton,
  projectId,
  hasChapters,
  focusModule,
  focusStatus,
}: {
  projectName: string;
  threadName: string;
  // Slot for the auto-draft trigger button — kept as a render prop so the
  // header stays a pure presentational component with no hook dependencies.
  autoDraftButton: ReactNode;
  // Optional: when provided, enables the "Open editor" shortcut button.
  projectId?: string;
  // Gate: show "Open editor" only once the project has at least one chapter,
  // so the link is never dangling for brand-new projects.
  hasChapters?: boolean;
  // Design's focus bar: the module the conversation is currently focused on
  // (project.focus, falling back to current_module) + its workflow status.
  focusModule?: string;
  focusStatus?: string;
}) {
  const focusLabel = MODULES.find(m => m.id === focusModule)?.label;
  const tag = focusStatus ? STATUS_TAG[focusStatus] ?? STATUS_TAG.in_progress : null;

  return (
    <header className="border-b border-ink-200 bg-white px-5 py-3 flex items-center gap-3 min-h-[56px]">
      <Link
        href="/"
        aria-label="Back to home"
        className="w-8 h-8 rounded-full bg-ink-100 text-ink-700 hover:bg-ink-200 inline-flex items-center justify-center shrink-0 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
      </Link>

      {focusModule && (
        <span className="px-[9px] py-1 rounded-lg bg-primary-50 text-primary-700 font-serif font-extrabold text-[12.5px] tracking-[0.04em] shrink-0">
          {focusModule}
        </span>
      )}
      <div className="flex items-baseline gap-2 min-w-0 flex-1">
        {focusLabel && (
          <span className="text-[15px] font-bold text-ink-900 whitespace-nowrap">{focusLabel}</span>
        )}
        {tag && (
          <span className={`self-center px-2.5 py-[3px] rounded-full text-[11px] font-bold uppercase tracking-[0.02em] whitespace-nowrap ${tag.cls}`}>
            {tag.label}
          </span>
        )}
        <span className="text-[13px] text-ink-500 truncate">
          {focusLabel ? "· " : ""}{projectName}
        </span>
        <span className="text-ink-300 shrink-0">·</span>
        <span className="text-sm text-ink-500 truncate">{threadName}</span>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        {/* "Open editor" is only shown once chapters exist — avoids a dead
            link for new projects that have no content to edit yet. */}
        {hasChapters && projectId && (
          <Link
            href={`/chat/projects/${projectId}/editor`}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-[13px] font-semibold border-[1.5px] border-primary-600 text-primary-600 rounded-full hover:bg-primary-50 transition-colors"
          >
            <PenSquare className="w-3.5 h-3.5" /> Open editor
          </Link>
        )}
        {autoDraftButton}
      </div>
    </header>
  );
}
