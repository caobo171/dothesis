import Link from "next/link";
import { ReactNode, useContext, useState } from "react";
import { ArrowLeft, Bell, ChevronDown, Download, FileDown, History, Loader2, Menu, PanelRight, PenSquare, Sparkles } from "lucide-react";

import { useMe } from "@/app/lib/use-me";
import { useT } from "@/app/lib/i18n/LocaleProvider";
import { triggerExportDownload } from "@/app/lib/api";
import { useArtifactDownload } from "./hooks/useArtifactDownload";

// Export is agent-driven: the user picks any modules in the ExportModulesModal,
// and we ask the agent to call `export_docx(scope="M1,M3,…")` — which composes
// the chosen module(s) into ONE professor-ready doc and records it in the
// Exports list tagged with that scope (never dumped in M5). The docx/pdf show up
// in the Exports panel + as a download card in chat.
function _exportPrompt(modules: string[]): string {
  // "full" → the complete 6-chapter thesis (compose_all_sections), not a
  // combination of module write-ups.
  if (modules.length === 1 && modules[0] === "full") {
    return (
      "Export my FULL thesis as a polished, professor-ready Word document — " +
      'call export_docx with scope "full" (all chapters: introduction, ' +
      "literature review, methodology, results, discussion, conclusion, plus " +
      "the reference list)."
    );
  }
  const scope = modules.join(",");
  const list = modules.join(", ");
  const noun = modules.length > 1 ? "modules" : "module";
  return (
    `Export my ${list} ${noun} as one polished, professor-ready Word document ` +
    `— call export_docx with scope "${scope}". Use everything I've already ` +
    `committed for ${modules.length > 1 ? "those modules" : list}.`
  );
}
import { ChatSidebarContext } from "./ChatShellLayout";
import { ExportModulesModal } from "./ExportModulesModal";
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
  // Above the early return — the disabled branch below is a conditional exit,
  // and a hook after it would change hook order between renders.
  const { busy, error, start } = useArtifactDownload();
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
      aria-busy={busy}
      onClick={(e) => {
        e.preventDefault();
        void start(() => triggerExportDownload(docx.download_url));
      }}
      // Icon-only button, so the title carries the state — there is nowhere to
      // put a status line, and the error still needs somewhere to go.
      title={
        error
          ? `Download failed: ${error}`
          : busy
            ? "Preparing download…"
            : "Download final thesis (DOCX)"
      }
      className={`w-8 h-8 rounded-full inline-flex items-center justify-center transition-colors ${
        error ? "text-[#8E6B2A] hover:bg-[#F5EFE2]" : "text-primary-600 hover:bg-primary-50"
      }`}
    >
      {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
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
  onQuickPrompt,
  loading = false,
}: {
  projectName: string;
  threadName: string;
  /** The project hasn't arrived yet — show a skeleton instead of placeholder
   *  punctuation. */
  loading?: boolean;
  autoDraftButton: ReactNode;
  projectId?: string;
  hasChapters?: boolean;
  focusModule?: string;
  focusStatus?: string;
  /** M5 export artifacts (docx/pdf). When present, the Download button
   *  becomes a real link to the docx; otherwise it's disabled with a
   *  "no export yet" tooltip. */
  exportArtifacts?: { kind: string; download_url: string }[];
  /** Send a pre-defined prompt into the chat — Export-to-Word quick actions
   *  use it to ask the agent to export a module (export_docx scope). */
  onQuickPrompt?: (text: string) => void;
}) {
  const t = useT();
  const focusKey = MODULES.find(m => m.id === focusModule)?.labelKey;
  const focusLabel = focusKey ? t(focusKey) : undefined;
  const phase = focusModule ? PHASE_LABEL[focusModule] : undefined;
  const tag = focusStatus ? STATUS_TAG[focusStatus] ?? STATUS_TAG.in_progress : null;
  const me = useMe();
  const sidebar = useContext(ChatSidebarContext);
  const [quickOpen, setQuickOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
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

        {/* Quick actions — collapses Autopilot + history/export/notifications
            into one menu so the header isn't crowded (esp. on mobile). */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setQuickOpen(o => !o)}
            aria-haspopup="menu"
            aria-expanded={quickOpen}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-primary-600 text-white text-[12.5px] font-semibold hover:bg-primary-700 transition-colors"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Quick actions</span>
            <ChevronDown className="w-3 h-3" />
          </button>

          {quickOpen && (
            <>
              {/* click-away */}
              <div className="fixed inset-0 z-40" onClick={() => setQuickOpen(false)} aria-hidden="true" />
              <div
                role="menu"
                className="absolute right-0 mt-2 z-50 w-64 rounded-2xl border border-ink-200 bg-white shadow-xl p-2"
                onClick={() => setQuickOpen(false)}
              >
                <div className="px-2 pt-1 pb-2 text-[10.5px] uppercase tracking-[0.06em] font-bold text-ink-400">
                  Run
                </div>
                {/* Autopilot (renamed from Auto approve) */}
                <div className="px-1 pb-2">{autoDraftButton}</div>

                {onQuickPrompt && (
                  <>
                    <div className="px-2 pt-1 pb-1 text-[10.5px] uppercase tracking-[0.06em] font-bold text-ink-400 border-t border-ink-100">
                      Export to Word
                    </div>
                    {/* One action → opens the module picker (choose any modules;
                        they're combined into one .docx). */}
                    <button
                      type="button"
                      onClick={() => setExportOpen(true)}
                      className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-[13px] text-ink-800 hover:bg-ink-50 text-left"
                    >
                      <FileDown className="w-4 h-4 text-ink-500" />
                      <span>Export modules → .docx…</span>
                    </button>
                  </>
                )}

                <div className="px-2 pt-1 pb-1 text-[10.5px] uppercase tracking-[0.06em] font-bold text-ink-400 border-t border-ink-100">
                  More
                </div>
                <ExportDownloadButton artifacts={exportArtifacts} />
                <button
                  type="button"
                  title="Version history"
                  className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-[13px] text-ink-800 hover:bg-ink-50 text-left"
                >
                  <History className="w-4 h-4 text-ink-500" /> Version history
                </button>
                <button
                  type="button"
                  title="Notifications"
                  className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-[13px] text-ink-800 hover:bg-ink-50 text-left"
                >
                  <span className="relative inline-flex">
                    <Bell className="w-4 h-4 text-ink-500" />
                    <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full bg-red-500" />
                  </span>
                  Notifications
                </button>
              </div>
            </>
          )}
        </div>

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

      {onQuickPrompt && (
        <ExportModulesModal
          open={exportOpen}
          onClose={() => setExportOpen(false)}
          onExport={(modules) => onQuickPrompt(_exportPrompt(modules))}
        />
      )}
    </header>
  );
}
