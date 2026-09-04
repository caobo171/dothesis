import Link from "next/link";
import { useContext } from "react";
import { ArrowLeft, Menu, PanelRight, PenSquare } from "lucide-react";

import { useMe } from "@/app/lib/use-me";
import { useT } from "@/app/lib/i18n/LocaleProvider";

import { ChatSidebarContext } from "./ChatShellLayout";
import { MODULES } from "./HomeDashboard";


// Pill palette for the focus-bar status tag.
const STATUS_TAG: Record<string, { label: string; cls: string }> = {
  in_progress:  { label: "In progress",   cls: "bg-primary-50 text-primary-700" },
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
 * Right cluster: Open editor link, vertical divider, user avatar + name +
 * tier. Quick actions (Auto Thesis, export, history, notifications) moved to
 * the bottom composer — see QuickActionsMenu.
 */
export function ChatHeader({
  projectName,
  threadName,
  projectId,
  hasChapters,
  focusModule,
  focusStatus,
  loading = false,
}: {
  projectName: string;
  threadName: string;
  /** The project hasn't arrived yet — show a skeleton instead of placeholder
   *  punctuation. */
  loading?: boolean;
  projectId?: string;
  hasChapters?: boolean;
  focusModule?: string;
  focusStatus?: string;
}) {
  const t = useT();
  const focusKey = MODULES.find(m => m.id === focusModule)?.labelKey;
  const focusLabel = focusKey ? t(focusKey) : undefined;
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
        {loading ? (
          // A skeleton, not the literal "…" this used to fall back to. With no
          // focus chip and no label yet, that rendered a bare "· … · …" —
          // punctuation around nothing, which reads as a broken header rather
          // than one that is still loading.
          <span className="h-3 w-40 rounded-full bg-ink-200/80 animate-pulse shrink-0"
                aria-label="Loading thesis" />
        ) : (
          <>
            <span className="text-ink-300 shrink-0">·</span>
            <span className="text-[12.5px] text-ink-500 truncate"
                  title={`${projectName} · ${threadName}`}>
              {projectName} · {threadName}
            </span>
          </>
        )}
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

        {/* Quick actions moved to the bottom composer (ChatInput →
            QuickActionsMenu) to free header space; see that component. */}

        <span className="hidden lg:block w-px h-[22px] bg-ink-200 mx-1" />

        {/* User identity — avatar only. The name + tier text was long and
            redundant in the header, so it's dropped; the full name + tier show
            on hover (title) and stay on the account page. */}
        <span
          className="w-[30px] h-[30px] rounded-full bg-ink-800 inline-flex items-center justify-center text-white font-bold text-[12px] shrink-0 ml-1"
          title={`${userName} · ${userTier}`}
          aria-label={`${userName}, ${userTier}`}
        >
          {userInitials}
        </span>
      </div>
    </header>
  );
}
