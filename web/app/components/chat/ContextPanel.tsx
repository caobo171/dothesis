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
import { Skeleton } from "@/app/components/ui/skeleton";


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

// Workflow position only. `needs_review` was a fourth value here; it outranked
// `done`, replaced the module's progress bar with an amber warning, and the
// roadmap sent the student back to clear it before anything could move on.
// Staleness is now a separate, passive fact — see `stale` below.
type SectionStatus = "done" | "in_progress" | "locked";


/**
 * Right rail — live context_store viewer. Mirrors the design's
 * `ContextPanel` from babel-05-ec044a3a.jsx:
 *
 *   - Header strip: "Workspace" + `context_store.json` chip + "{ }"
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
  staleModules,
  threadCredits,
  onSendMessage,
  roadmapRefreshKey,
  loading = false,
}: {
  projectId?: string;
  /**
   * Project row hasn't landed yet. Without this the panel is given a null
   * store and every card says "Topic not set yet" — the same empty-state
   * flash the chat pane used to do, next to a thread that is still a
   * skeleton. Chrome (the "Workspace" header) stays; the cards pulse.
   */
  loading?: boolean;
  contextStore: ContextStore;
  uploads: UploadItem[];
  currentModule?: string;
  moduleStatus?: ModuleStatusMap;
  /** Modules whose content predates a later upstream edit. Advisory: it adds a
   *  note inside the card and changes nothing else. */
  staleModules?: string[];
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
    // Tolerate a `needs_review` still sitting in an unmigrated row or an
    // in-flight response: it always meant "was done, then invalidated", so it
    // reads as done and the staleness shows up through staleModules instead.
    if (raw === "needs_review" || raw === "done" || data?.confirmed_at) return "done";
    if (raw === "in_progress" || id === currentModule) return "in_progress";
    return "locked";
  };
  const isStale = (id: keyof ModuleStatusMap) =>
    (staleModules ?? []).includes(id) || moduleStatus?.[id] === "needs_review";

  return (
    <aside
      // Fluid width — the parent (ChatShellLayout) sets the width via a
      // drag handle now. min-w-0 lets long titles/labels wrap inside the
      // narrower lower bound (~280px).
      className="w-full min-w-0 border-l border-ink-200 bg-white h-full flex flex-col overflow-hidden"
      data-testid="context-panel"
      aria-busy={loading || undefined}
    >
      {/* Header */}
      <div className="px-[18px] py-3.5 border-b border-ink-200 flex items-center gap-2">
        {/* "Workspace", not "Context store": the panel is the container for two
            file groups now labelled Context (inputs) and Outputs, so reusing
            "Context" for the whole panel would clash with the Context card
            inside it. The context_store.json chip below keeps the underlying
            name visible for anyone who knows it. */}
        <span className="text-[14px] font-bold shrink-0 whitespace-nowrap">Workspace</span>
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
        {loading ? (
          <ContextPanelSkeleton />
        ) : showRaw ? (
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
              stale={isStale("M1")}
              substeps={substepsOf("M1")}
            >
              <M1Body data={contextStore.m1_topic} />
            </CtxSection>

            <CtxSection
              label="M2 · Gaps & hypotheses"
              moduleId="M2"
              status={sectionStatus("M2", contextStore.m2_literature)}
              stale={isStale("M2")}
              substeps={substepsOf("M2")}
            >
              <M2Body data={contextStore.m2_literature} />
            </CtxSection>

            <CtxSection
              label="M3 · Methodology & model"
              moduleId="M3"
              status={sectionStatus("M3", contextStore.m3_design)}
              stale={isStale("M3")}
              substeps={substepsOf("M3")}
            >
              <M3Body data={contextStore.m3_design} />
            </CtxSection>

            <CtxSection
              label="M4 · Analysis"
              moduleId="M4"
              status={sectionStatus("M4", contextStore.m4_analysis)}
              stale={isStale("M4")}
              substeps={substepsOf("M4")}
            >
              <div className="text-[12.5px] text-ink-500 leading-snug">
                Soft-locked — you can ask or start; the agent will prompt if a dependency is missing.
              </div>
            </CtxSection>

            {/* One writing step, not two — the discussion of findings is
                written INSIDE the closing chapter rather than as a chapter
                of its own (agent/roadmap.py ROADMAP["M5"]). */}
            <CtxSection
              label="M5 · Conclusion"
              moduleId="M5"
              status={sectionStatus("M5", contextStore.m5_writing)}
              stale={isStale("M5")}
              substeps={substepsOf("M5")}
            >
              <M5Body data={contextStore.m5_writing} />
            </CtxSection>

            {projectId && <ExportsSection projectId={projectId} />}

            {uploads.length > 0 && (
              <CtxSection label={`Context (${uploads.length})`} status="in_progress">
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


// Same card stack the loaded panel uses (NEXT + five modules + Exports),
// so the rail doesn't jump when the project lands. Pulse bars, not the
// empty-module sentences — those are a claim about state we don't have yet.
function ContextPanelSkeleton() {
  return (
    <div
      className="flex flex-col gap-3"
      data-testid="context-panel-skeleton"
      aria-label="Loading workspace"
    >
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} className="border border-ink-200 rounded-xl bg-white px-3.5 py-3">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-ink-200 animate-pulse shrink-0" />
            <Skeleton className="h-3 w-36" />
          </div>
          <Skeleton className="h-2.5 w-full mt-3" />
          <Skeleton className="h-2.5 w-2/3 mt-2" />
        </div>
      ))}
    </div>
  );
}


// ---- per-module section card ---------------------------------------

function CtxSection({
  label,
  status,
  stale = false,
  moduleId,
  substeps = [],
  children,
}: {
  label: string;
  status: SectionStatus;
  /** Content predates a later upstream edit. Renders a note inside the card;
   *  deliberately does NOT touch the status dot or the step bar. */
  stale?: boolean;
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
        <StepBar substeps={substeps} />
        <span className="text-ink-400 text-[11px]">{collapsed ? "▸" : "▾"}</span>
      </button>
      {!collapsed && (
        <div className="px-3.5 pb-3.5">
          {stale && (
            // A note, not a gate. The module keeps its status and its progress
            // bar; this only tells the student that something it was built on
            // changed afterwards, so they can decide whether to revisit it.
            // Nothing here blocks export or re-orders what comes next.
            <div className="mb-2 text-[11px] text-ink-500 flex items-start gap-1.5">
              <AlertTriangle className="w-3 h-3 mt-[2px] shrink-0" />
              <span>May be out of date — something upstream changed after this
                was written. Ask in chat to bring it up to date.</span>
            </div>
          )}
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
  full: "Toàn bộ luận văn", M1: "M1 · Chủ đề", M2: "M2 · Tổng quan",
  M3: "M3 · Phương pháp", M4: "M4 · Phân tích", M5: "M5 · Kết luận",
};

// FIVE chapters, not six: `conclusion` IS Chương 5 now (the discussion of
// findings is written inside it), so it takes the "Chương 5" tag that used to
// belong to the retired `discussion` key — matching orchestrator.tools
// .m5_writing.M5_CHAPTER_TITLES_VI.
const _CHAPTER_SCOPE_LABEL: Record<string, string> = {
  intro: "Chương 1", lit_review: "Chương 2", methodology: "Chương 3",
  results: "Chương 4", conclusion: "Chương 5",
};

export function formatExportScope(scope: string): string {
  const value = (scope || "").trim();
  if (!value) return "Tài liệu";
  if (value === "full") return "Toàn bộ luận văn";
  if (value.toLowerCase().startsWith("chapter:")) {
    const names = value.slice(8).split("|").map(name => name.trim().toLowerCase()).filter(Boolean);
    if (names.join("|") === "intro|lit_review|methodology") return "Chương 1–3";
    return names.map(name => _CHAPTER_SCOPE_LABEL[name] ?? name).join(" + ");
  }
  return value.split(",").map(part => part.trim()).filter(Boolean)
    .map(module => _SCOPE_LABEL[module] ?? module).join(" + ");
}

function ExportsSection({ projectId }: { projectId: string }) {
  // Fetch the project's exports list (newest first). Revalidates on focus so a
  // freshly-agent-generated export shows up without a manual reload.
  const { data } = useSWR<ExportRow[]>(`/projects/${projectId}/exports/list`, fetcher);
  const rows = data ?? [];
  return (
    <CtxSection label={`Outputs${rows.length ? ` (${rows.length})` : ""}`} status="in_progress">
      {rows.length === 0 ? (
        <EmptyHint text="No outputs yet — ask to export a module or the full thesis, or use Quick actions → Export to Word." />
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
      <span className="text-[11.5px] font-semibold text-primary-700 bg-primary-50 px-1.5 py-0.5 rounded truncate min-w-0">
        {formatExportScope(row.scope)}
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
