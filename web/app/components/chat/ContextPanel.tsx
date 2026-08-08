"use client";

import { useState } from "react";
import useSWR from "swr";
import { AlertTriangle, Clock, Coins, Download, Loader2 } from "lucide-react";

import { FileTypeIcon } from "./FileTypeIcon";
// The per-module slice renderers live in ModuleSlices now — the reconstructed-
// modules card renders the SAME components, so a backfilled M3 looks exactly
// like a live M3 (mermaid model included) instead of a second, worse view.
import { EmptyHint, M1Body, M2Body, M3Body, M5Body } from "./ModuleSlices";
import { RoadmapPanel, StepBar, StepList, useRoadmap, type Sub } from "./RoadmapPanel";
import { useArtifactDownload } from "./hooks/useArtifactDownload";
import {
  triggerExportDownload,
  triggerUploadDownload,
  swrFetcher as fetcher,
} from "@/app/lib/api";


// ---- types (kept stable so callers don't change) ---------------------

export type ContextStore = {
  m1_topic: Record<string, any> | null;
  m2_literature: Record<string, any> | null;
  m3_design: Record<string, any> | null;
  m4_analysis: Record<string, any> | null;
  m5_writing: Record<string, any> | null;
};

export type UploadItem = {
  id: string;
  filename: string;
  size_bytes: number;
  mime_type: string;
  page_count: number | null;
  uploaded_at: string;
};

export type ModuleStatusMap = Partial<Record<"M1" | "M2" | "M3" | "M4" | "M5", string>>;

type SectionStatus = "done" | "in_progress" | "needs_review" | "locked";


/**
 * Right rail — live context_store viewer. Mirrors the design's
 * `ContextPanel` from babel-05-ec044a3a.jsx:
 *
 *   - Header strip: "Context store" + `context_store.json` chip + "{ }"
 *     raw JSON button
 *   - Stack of `CtxSection` cards, one per module: a color dot per
 *     status, label, optional ⚠ marker, and a "▸" toggle button
 *   - Inside each card: small caps field labels with the actual values
 *     pulled from the slice (research_title, research_questions,
 *     research_gaps, hypotheses, methodology, etc.)
 *   - Footer strip: snapshot timestamp + "View history" link
 *
 * The workflow rail (M1–M5 progress) used to live in this same panel —
 * it moved to WorkflowSidebar on the LEFT. This pane is now read-only
 * data inspection: what the agent has committed to your project state.
 */
export function ContextPanel({
  projectId,
  contextStore,
  uploads,
  currentModule,
  moduleStatus,
  threadCredits,
  onSendMessage,
  roadmapRefreshKey,
}: {
  projectId?: string;
  contextStore: ContextStore;
  uploads: UploadItem[];
  currentModule?: string;
  moduleStatus?: ModuleStatusMap;
  /** Total credits spent in the current thread — shown in the header. */
  threadCredits?: number;
  /** F2: when the host can post into chat, the roadmap Next-card CTAs use this
   *  to one-click act. Optional — the panel is read-only without it. */
  onSendMessage?: (text: string) => void;
  /** F2: bump to force the roadmap to re-fetch (e.g. after a turn completes). */
  roadmapRefreshKey?: number;
}) {
  const [showRaw, setShowRaw] = useState(false);
  // Fetched once here, then split two ways: the Next card stays in
  // RoadmapPanel, and each module's sub-steps ride on that module's own card
  // instead of a second list above them.
  const roadmap = useRoadmap(projectId, roadmapRefreshKey);
  const substepsOf = (id: string): Sub[] =>
    roadmap?.modules?.find(m => m.id === id)?.substeps ?? [];

  const sectionStatus = (id: keyof ModuleStatusMap, data: Record<string, any> | null): SectionStatus => {
    const raw = moduleStatus?.[id];
    if (raw === "needs_review") return "needs_review";
    if (raw === "done" || data?.confirmed_at) return "done";
    if (raw === "in_progress" || id === currentModule) return "in_progress";
    return "locked";
  };

  return (
    <aside
      // Fluid width — the parent (ChatShellLayout) sets the width via a
      // drag handle now. min-w-0 lets long titles/labels wrap inside the
      // narrower lower bound (~280px).
      className="w-full min-w-0 border-l border-ink-200 bg-white h-full flex flex-col overflow-hidden"
      data-testid="context-panel"
    >
      {/* Header */}
      <div className="px-[18px] py-3.5 border-b border-ink-200 flex items-center gap-2">
        <span className="text-[14px] font-bold shrink-0 whitespace-nowrap">Context store</span>
        <span className="inline-flex items-center min-w-0 px-2 py-0.5 rounded-full bg-primary-50 text-primary-700 text-[11px] font-semibold font-mono truncate">
          context_store.json
        </span>
        <span className="flex-1 min-w-[6px]" />
        {typeof threadCredits === "number" && threadCredits > 0 && (
          <span
            title="Credits spent in this thread"
            className="inline-flex items-center gap-1 shrink-0 whitespace-nowrap text-[11px] font-semibold text-amber-600"
          >
            <Coins className="w-3 h-3" aria-hidden />
            {threadCredits.toLocaleString()}
          </span>
        )}
        <button
          type="button"
          onClick={() => setShowRaw(s => !s)}
          aria-label="Toggle raw JSON"
          title="Raw JSON"
          className="w-7 h-7 shrink-0 rounded-md text-ink-500 hover:bg-ink-100 hover:text-ink-900 inline-flex items-center justify-center text-[13px] font-mono transition-colors"
        >
          {"{}"}
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-4 py-3 flex flex-col gap-3">
        {showRaw ? (
          <pre className="text-[11.5px] font-mono text-ink-700 bg-ink-50 rounded-lg p-3 leading-snug overflow-x-auto">
            {JSON.stringify(contextStore, null, 2)}
          </pre>
        ) : (
          <>
            {/* F2: the derived coaching roadmap + Next card leads the student
                from real state. Mounted above the per-module cards. */}
            {projectId && (
              <RoadmapPanel data={roadmap} onSendMessage={onSendMessage} />
            )}
            <CtxSection
              label="M1 · Topic & questions"
              moduleId="M1"
              status={sectionStatus("M1", contextStore.m1_topic)}
              substeps={substepsOf("M1")}
            >
              <M1Body data={contextStore.m1_topic} />
            </CtxSection>

            <CtxSection
              label="M2 · Gaps & hypotheses"
              moduleId="M2"
              status={sectionStatus("M2", contextStore.m2_literature)}
              substeps={substepsOf("M2")}
            >
              <M2Body data={contextStore.m2_literature} />
            </CtxSection>

            <CtxSection
              label="M3 · Methodology & model"
              moduleId="M3"
              status={sectionStatus("M3", contextStore.m3_design)}
              substeps={substepsOf("M3")}
            >
              <M3Body data={contextStore.m3_design} />
            </CtxSection>

            <CtxSection
              label="M4 · Analysis"
              moduleId="M4"
              status={sectionStatus("M4", contextStore.m4_analysis)}
              substeps={substepsOf("M4")}
            >
              <div className="text-[12.5px] text-ink-500 leading-snug">
                Soft-locked — you can ask or start; the agent will prompt if a dependency is missing.
              </div>
            </CtxSection>

            <CtxSection
              label="M5 · Writing"
              moduleId="M5"
              status={sectionStatus("M5", contextStore.m5_writing)}
              substeps={substepsOf("M5")}
            >
              <M5Body data={contextStore.m5_writing} />
            </CtxSection>

            {projectId && <ExportsSection projectId={projectId} />}

            {uploads.length > 0 && (
              <CtxSection label={`Uploads (${uploads.length})`} status="in_progress">
                <div className="space-y-1.5">
                  {uploads.slice(0, 5).map(u => <UploadRow key={u.id} upload={u} />)}
                  {uploads.length > 5 && (
                    <div className="text-[11.5px] text-ink-400 pt-1">
                      +{uploads.length - 5} more…
                    </div>
                  )}
                </div>
              </CtxSection>
            )}
          </>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2.5 border-t border-ink-200 bg-ink-50 flex items-center gap-2 text-[11.5px] text-ink-500">
        <Clock className="w-3 h-3" />
        <span>Live · auto-saved</span>
        <span className="flex-1" />
        <button
          type="button"
          className="text-primary-600 font-semibold text-[12px] hover:underline"
        >
          View history
        </button>
      </div>
    </aside>
  );
}


// ---- per-module section card ---------------------------------------

function CtxSection({
  label,
  status,
  moduleId,
  substeps = [],
  children,
}: {
  label: string;
  status: SectionStatus;
  /** This module's roadmap sub-steps. Shown as a bar in the header (with the
   *  step names on hover) and in full when the card is expanded — replacing
   *  the separate strikethrough checklist that listed every module a second
   *  time above these cards. */
  substeps?: Sub[];
  /** Stable machine-readable hook for E2E assertions ("M1".."M5"). The
   *  status dot is a Tailwind class — style-coupled and unassertable — so
   *  tests read data-status instead (2026-07-08 e2e-testing spec). Only the
   *  five module cards pass this; the Exports/Uploads cards omit it so they
   *  get no testid and their data-status is inert. */
  moduleId?: string;
  children: React.ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const dot = STATUS_DOT[status];
  return (
    <div
      className="border border-ink-200 rounded-xl bg-white"
      data-testid={moduleId ? `ctx-${moduleId}` : undefined}
      data-status={status}
    >
      <button
        type="button"
        onClick={() => setCollapsed(c => !c)}
        className="w-full px-3.5 pt-3 pb-2 flex items-center gap-2 text-left hover:bg-ink-50/60 transition-colors rounded-t-xl"
      >
        <span className={`w-2 h-2 rounded-full shrink-0 ${dot}`} />
        <span className="text-[12.5px] font-bold text-ink-800">{label}</span>
        <span className="flex-1" />
        {status !== "needs_review" && <StepBar substeps={substeps} />}
        {status === "needs_review" && (
          // The bare ⚠ icon left users unsure what it meant or what to do.
          // Label it + explain on hover: needs_review = a dependency hole the
          // agent flagged (e.g. a hypothesis with no backing gap). The fix is
          // to revisit the module in chat, where the agent walks the reconcile.
          <span
            className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-600"
            title="Needs review — something this module depends on changed upstream (e.g. a hypothesis with no backing gap). Open this module in chat and the agent will help you reconcile it."
          >
            <AlertTriangle className="w-3.5 h-3.5" />
            Needs review
          </span>
        )}
        <span className="text-ink-400 text-[11px]">{collapsed ? "▸" : "▾"}</span>
      </button>
      {!collapsed && (
        <div className="px-3.5 pb-3.5">
          <StepList substeps={substeps} />
          {children}
        </div>
      )}
    </div>
  );
}

const STATUS_DOT: Record<SectionStatus, string> = {
  done:         "bg-emerald-600",
  in_progress:  "bg-primary-600",
  needs_review: "bg-amber-600",
  locked:       "bg-ink-300",
};


// --- Exports (module-agnostic) ---

type ExportRow = {
  id: string;
  scope: string;   // "full" | "M1".."M4"
  kind: string;    // "docx" | "pdf"
  filename: string;
  size_bytes: number;
  created_at: string | null;
  download_url: string;
};

const _SCOPE_LABEL: Record<string, string> = {
  full: "Full thesis", M1: "M1 Topic", M2: "M2 Literature",
  M3: "M3 Design", M4: "M4 Analysis", M5: "M5 Writing",
};

function ExportsSection({ projectId }: { projectId: string }) {
  // Fetch the project's exports list (newest first). Revalidates on focus so a
  // freshly-agent-generated export shows up without a manual reload.
  const { data } = useSWR<ExportRow[]>(`/projects/${projectId}/exports/list`, fetcher);
  const rows = data ?? [];
  return (
    <CtxSection label={`Exports${rows.length ? ` (${rows.length})` : ""}`} status="in_progress">
      {rows.length === 0 ? (
        <EmptyHint text="No exports yet — ask to export a module or the full thesis, or use Quick actions → Export to Word." />
      ) : (
        <div className="space-y-1.5">
          {rows.map(r => <ExportRowItem key={r.id} row={r} />)}
        </div>
      )}
    </CtxSection>
  );
}

function ExportRowItem({ row }: { row: ExportRow }) {
  const size =
    row.size_bytes >= 1024 * 1024
      ? `${(row.size_bytes / (1024 * 1024)).toFixed(1)} MB`
      : `${(row.size_bytes / 1024).toFixed(0)} KB`;
  // Was `void triggerExportDownload(...)`: the token mint showed nothing while
  // in flight and swallowed its own failure. The spinner takes the file icon's
  // slot so the row keeps its width.
  const { busy, error, start } = useArtifactDownload();
  return (
    <>
    <a
      href={row.download_url}
      download
      aria-busy={busy}
      onClick={(e) => {
        e.preventDefault();
        void start(() => triggerExportDownload(row.download_url));
      }}
      className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg border transition-colors ${
        busy
          ? "border-primary-300 bg-primary-50 cursor-progress"
          : "border-ink-200 bg-white hover:border-primary-300 hover:bg-primary-50"
      }`}
    >
      {busy ? (
        <Loader2 className="w-[18px] h-[22px] shrink-0 text-primary-600 animate-spin" aria-hidden />
      ) : (
        <FileTypeIcon kind={row.kind} className="w-[18px] h-[22px] shrink-0" />
      )}
      <span className="font-serif text-[12px] font-extrabold text-ink-900 shrink-0">
        {row.kind.toUpperCase()}
      </span>
      <span className="text-[10.5px] uppercase tracking-[0.04em] font-bold text-primary-700 bg-primary-50 px-1.5 py-0.5 rounded shrink-0">
        {row.scope === "full"
          ? _SCOPE_LABEL.full
          : !row.scope.includes(",")
            ? (_SCOPE_LABEL[row.scope] ?? row.scope)
            : row.scope.split(",").map(s => s.trim()).join(" + ")}
      </span>
      <span className="text-ink-400 text-[11.5px] ml-auto shrink-0">{size}</span>
      <Download className="w-3.5 h-3.5 text-ink-400 shrink-0" aria-hidden />
    </a>
    {error && (
      <div className="text-[11px] text-[#8E6B2A] px-2.5 pt-1" role="alert">{error}</div>
    )}
    </>
  );
}

// Uploads row — same shape as ExportRowItem. Uses FileTypeIcon (red PDF band)
// instead of the old 📄 emoji, shows page count when present, and downloads via
// triggerUploadDownload (mints a scoped ?st= token → /uploads/{id}/download
// → S3 signed URL). Kind is derived from mime_type.
function UploadRow({ upload }: { upload: UploadItem }) {
  const kind = (upload.mime_type || "").includes("pdf") ? "pdf" : "file";
  const { busy, error, start } = useArtifactDownload();
  return (
    <>
    <button
      type="button"
      aria-busy={busy}
      onClick={() => void start(() => triggerUploadDownload(upload.id))}
      title={`Download ${upload.filename}`}
      className={`w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg border transition-colors text-left ${
        busy
          ? "border-primary-300 bg-primary-50 cursor-progress"
          : "border-ink-200 bg-white hover:border-primary-300 hover:bg-primary-50"
      }`}
    >
      {busy ? (
        <Loader2 className="w-[18px] h-[22px] shrink-0 text-primary-600 animate-spin" aria-hidden />
      ) : (
        <FileTypeIcon kind={kind} className="w-[18px] h-[22px] shrink-0" />
      )}
      <span className="text-[12.5px] text-ink-800 truncate flex-1 min-w-0">
        {upload.filename}
      </span>
      {upload.page_count != null && (
        <span className="text-[11px] text-ink-400 tabular-nums shrink-0">
          {upload.page_count}p
        </span>
      )}
      <Download className="w-3.5 h-3.5 text-ink-400 shrink-0" aria-hidden />
    </button>
    {error && (
      <div className="text-[11px] text-[#8E6B2A] px-2.5 pt-1" role="alert">{error}</div>
    )}
    </>
  );
}

