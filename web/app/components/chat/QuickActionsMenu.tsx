"use client";

import { ReactNode, useState } from "react";
import { Bell, ChevronDown, Download, FileDown, History, Loader2, Sparkles } from "lucide-react";

import { triggerExportDownload } from "@/app/lib/api";
import { useArtifactDownload } from "./hooks/useArtifactDownload";
import { ExportModulesModal } from "./ExportModulesModal";


// Export is agent-driven: the user picks any modules in the ExportModulesModal,
// and we ask the agent to call `export_docx(scope="M1,M3,…")` — which composes
// the chosen module(s) into ONE professor-ready doc and records it in the
// Outputs list tagged with that scope (never dumped in M5). The docx/pdf show up
// in the Outputs panel + as a download card in chat.
function _exportPrompt(modules: string[]): string {
  // "full" → the complete 5-chapter thesis (compose_all_sections), not a
  // combination of module write-ups. Five, not six: the discussion of
  // findings is written INSIDE the closing chapter (conclusion) rather than
  // as a chapter of its own.
  if (modules.length === 1 && modules[0] === "full") {
    return (
      "Export my FULL thesis as a polished, professor-ready Word document — " +
      'call export_docx with scope "full" (all chapters: introduction, ' +
      "literature review, methodology, results, conclusion, plus " +
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


// Menu ROW download of the auto-generated M5 export artifact — enabled only when
// M5 has produced one (auto-fires when M5 flips to done; see
// api/app/agent_state.py:_auto_export_m5). The /exports/{filename} route 302s to
// a signed S3 URL; the browser can't attach a body to <a> download links, so we
// mint a short-lived, scoped stream token on click and navigate with ?st=
// instead of leaking the long-lived JWT in the URL.
function ExportDownloadButton({
  artifacts,
}: {
  artifacts?: { kind: string; download_url: string }[];
}) {
  // Above the early return — the disabled branch below is a conditional exit,
  // and a hook after it would change hook order between renders.
  const { busy, error, start } = useArtifactDownload();
  const docx = artifacts?.find(a => a.kind === "docx") ?? artifacts?.[0];

  // "icon + words" row, matching every other entry in the menu — this was once
  // a round header icon, which rendered as a bare glyph with no label inside a
  // menu, its only explanation in a tooltip nobody hovers once a menu has the
  // pointer.
  const row = "w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-[13px] text-left";

  if (!docx) {
    return (
      <button
        type="button"
        disabled
        title="Chưa có bản xuất — hoàn thành M5 trước"
        className={`${row} text-ink-400 cursor-not-allowed`}
      >
        <Download className="w-4 h-4 text-ink-300 shrink-0" />
        <span>Tải luận văn (.docx)</span>
        <span className="ml-auto text-[11px] text-ink-400">chưa có</span>
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
      className={`${row} ${
        error ? "text-[#8E6B2A] hover:bg-[#F5EFE2]" : "text-ink-800 hover:bg-ink-50"
      }`}
    >
      {busy
        ? <Loader2 className="w-4 h-4 animate-spin text-ink-500 shrink-0" />
        : <Download className="w-4 h-4 text-ink-500 shrink-0" />}
      <span>Tải luận văn (.docx)</span>
      {(busy || error) && (
        <span className="ml-auto text-[11px] truncate max-w-[130px]">
          {error ? `Lỗi: ${error}` : "Đang chuẩn bị…"}
        </span>
      )}
    </a>
  );
}


/**
 * Quick actions — collapses Auto Thesis + export/history/notifications into one
 * menu. Lifted out of ChatHeader and into the bottom composer (ChatInput) to
 * reclaim header space; kept as its own component so there is one definition,
 * not a header copy and a composer copy that drift.
 *
 * `placement` controls which way the panel opens. In the composer it must open
 * "up" — a downward menu would be clipped by the viewport bottom the button
 * sits against.
 */
export function QuickActionsMenu({
  autoThesisButton,
  exportArtifacts,
  onQuickPrompt,
  placement = "down",
  disabled = false,
}: {
  /** Project-aware Auto Thesis trigger — rendered under the menu's "Run" head. */
  autoThesisButton: ReactNode;
  /** M5 export artifacts (docx/pdf) for the "Tải luận văn" download row. */
  exportArtifacts?: { kind: string; download_url: string }[];
  /** Send a pre-defined prompt into the chat — the Export-to-Word actions use
   *  it to ask the agent to export a module (export_docx scope). Menu's
   *  Export-to-Word section is hidden without it. */
  onQuickPrompt?: (text: string) => void;
  placement?: "up" | "down";
  disabled?: boolean;
}) {
  const [quickOpen, setQuickOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);

  const panelPos = placement === "up" ? "bottom-full mb-2" : "top-full mt-2";

  return (
    <div className="relative">
      {/* Secondary weight, NOT a solid-primary fill. Sitting in the composer
          next to Send, a filled primary button out-shouted the actual compose
          CTA — two buttons competing for "the main thing to click". A
          primary-TINTED outline keeps the AI/actions signal (sparkle + primary
          hue) while reading as subordinate to Send. */}
      <button
        type="button"
        onClick={() => setQuickOpen(o => !o)}
        disabled={disabled}
        aria-haspopup="menu"
        aria-expanded={quickOpen}
        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-[12.5px] font-semibold transition-colors disabled:opacity-50 ${
          quickOpen
            ? "border-primary-300 text-primary-700 bg-primary-100"
            : "border-primary-200 text-primary-700 bg-primary-50 hover:bg-primary-100"
        }`}
      >
        <Sparkles className="w-3.5 h-3.5" />
        <span className="hidden sm:inline">Quick actions</span>
        <ChevronDown className={`w-3 h-3 ${placement === "up" ? "rotate-180" : ""}`} />
      </button>

      {quickOpen && (
        <>
          {/* click-away */}
          <div className="fixed inset-0 z-40" onClick={() => setQuickOpen(false)} aria-hidden="true" />
          <div
            role="menu"
            className={`absolute right-0 ${panelPos} z-50 w-64 rounded-2xl border border-ink-200 bg-white shadow-xl p-2`}
            onClick={() => setQuickOpen(false)}
          >
            <div className="px-2 pt-1 pb-2 text-[10.5px] uppercase tracking-[0.06em] font-bold text-ink-400">
              Run
            </div>
            {/* Auto Thesis */}
            <div className="px-1 pb-2">{autoThesisButton}</div>

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

      {onQuickPrompt && (
        <ExportModulesModal
          open={exportOpen}
          onClose={() => setExportOpen(false)}
          onExport={(modules) => onQuickPrompt(_exportPrompt(modules))}
        />
      )}
    </div>
  );
}
