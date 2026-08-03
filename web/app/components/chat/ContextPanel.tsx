"use client";

import { useState } from "react";
import useSWR from "swr";
import { AlertTriangle, Clock, Coins, Download, ExternalLink, Loader2 } from "lucide-react";

import { SliceModal } from "./SliceModal";
import { Mermaid } from "./Mermaid";
import { FileTypeIcon } from "./FileTypeIcon";
import { RoadmapPanel } from "./RoadmapPanel";
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
              <RoadmapPanel
                projectId={projectId}
                onSendMessage={onSendMessage}
                refreshKey={roadmapRefreshKey}
              />
            )}
            <CtxSection
              label="M1 · Topic & questions"
              moduleId="M1"
              status={sectionStatus("M1", contextStore.m1_topic)}
            >
              <M1Body data={contextStore.m1_topic} />
            </CtxSection>

            <CtxSection
              label="M2 · Gaps & hypotheses"
              moduleId="M2"
              status={sectionStatus("M2", contextStore.m2_literature)}
            >
              <M2Body data={contextStore.m2_literature} />
            </CtxSection>

            <CtxSection
              label="M3 · Methodology & model"
              moduleId="M3"
              status={sectionStatus("M3", contextStore.m3_design)}
            >
              <M3Body data={contextStore.m3_design} />
            </CtxSection>

            <CtxSection
              label="M4 · Analysis"
              moduleId="M4"
              status={sectionStatus("M4", contextStore.m4_analysis)}
            >
              <div className="text-[12.5px] text-ink-500 leading-snug">
                Soft-locked — you can ask or start; the agent will prompt if a dependency is missing.
              </div>
            </CtxSection>

            <CtxSection
              label="M5 · Writing"
              moduleId="M5"
              status={sectionStatus("M5", contextStore.m5_writing)}
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
  children,
}: {
  label: string;
  status: SectionStatus;
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
      {!collapsed && <div className="px-3.5 pb-3.5">{children}</div>}
    </div>
  );
}

const STATUS_DOT: Record<SectionStatus, string> = {
  done:         "bg-emerald-600",
  in_progress:  "bg-primary-600",
  needs_review: "bg-amber-600",
  locked:       "bg-ink-300",
};


// ---- per-section body renderers ------------------------------------

function FieldLabel({
  name,
  count,
  top = false,
}: {
  name: string;
  count?: number | string;
  // When `top` is true the label is the FIRST field inside a section card
  // — no top margin. Subsequent labels in the same card pass top={false}
  // (the default) so they get breathing room between groups.
  top?: boolean;
}) {
  return (
    <div
      className={`text-[11px] uppercase tracking-[0.05em] text-ink-500 font-semibold ${
        top ? "" : "mt-3"
      }`}
    >
      {name}
      {count != null && <> ({count})</>}
    </div>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex gap-2.5 items-baseline">
      <span className="min-w-[80px] text-ink-500 text-[12.5px]">{k}</span>
      <span className="flex-1 text-ink-800 text-[12.5px] font-medium">{v}</span>
    </div>
  );
}


function M5Body({ data }: { data: Record<string, any> | null }) {
  if (!data) {
    return (
      <EmptyHint text="Writing hasn't started — M5 builds the final docx/pdf from M1–M4 once those are done." />
    );
  }
  // Exports moved out of M5 into the dedicated module-agnostic Exports section
  // (a per-module export shouldn't appear under M5). M5Body now only shows the
  // writing progress (chapters / draft sections).
  const chapters = (data.chapters || {}) as Record<string, unknown>;
  const chapterCount = Object.keys(chapters).length;
  const finalSections = Array.isArray(data.final_sections) ? data.final_sections : [];
  if (chapterCount === 0 && finalSections.length === 0) {
    return (
      <EmptyHint text="Writing hasn't started — M5 builds the final docx/pdf from M1–M4 once those are done." />
    );
  }
  return (
    <>
      {chapterCount > 0 && (
        <>
          <FieldLabel name="chapters" count={chapterCount} top />
          <div className="text-[12.5px] text-ink-600 mt-1">
            {chapterCount}/6 chapters written
          </div>
        </>
      )}
      {finalSections.length > 0 && chapterCount === 0 && (
        <>
          <FieldLabel name="final_sections" count={finalSections.length} top />
          <div className="text-[12.5px] text-ink-600 mt-1">
            {finalSections.length} sections in draft
          </div>
        </>
      )}
    </>
  );
}

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

function M1Body({ data }: { data: Record<string, any> | null }) {
  // Click-to-expand like the other slices: the inline card shows title + RQs,
  // but a topic also carries field / scope / objectives that don't fit — open
  // the full detail in the centered SliceModal.
  const [modalOpen, setModalOpen] = useState(false);
  if (!data) return <EmptyHint text="Topic not set yet — start in M1." />;
  const title = data.research_title;
  const rqs = (data.research_questions || []) as string[];
  if (!title && rqs.length === 0) {
    return <EmptyHint text="No M1 data committed yet." />;
  }
  return (
    <>
      <button
        type="button"
        onClick={() => setModalOpen(true)}
        className="block w-full text-left -mx-1 px-1 py-0.5 rounded-md hover:bg-primary-50 transition-colors"
      >
        {title && (
          <>
            <FieldLabel name="research_title" top />
            <div className="font-serif text-[14px] leading-[1.45] text-ink-900 mt-1">
              {title}
            </div>
          </>
        )}
        {rqs.length > 0 && (
          <>
            <FieldLabel name="research_questions" count={rqs.length} />
            <ol className="list-decimal pl-5 mt-1.5 text-[12.5px] text-ink-700 leading-[1.45] space-y-0.5">
              {rqs.map((q, i) => <li key={i}>{q}</li>)}
            </ol>
          </>
        )}
        <span className="mt-2 inline-flex items-center gap-1 text-[11.5px] text-primary-600 font-semibold">
          View full topic <ExternalLink className="w-3 h-3" />
        </span>
      </button>

      <SliceModal
        open={modalOpen}
        title="Topic & questions"
        subtitle="Title, scope, objectives, and research questions"
        onClose={() => setModalOpen(false)}
      >
        <TopicDetail data={data} />
      </SliceModal>
    </>
  );
}

function TopicDetail({ data }: { data: Record<string, any> }) {
  const title = data.research_title as string | undefined;
  const rqs = (data.research_questions || []) as string[];
  const objectives = (data.objectives || []) as string[];
  // Scalar M1 fields rendered as labeled rows when present.
  const scalars: Array<[string, string]> = [
    ["Field", data.field],
    ["Research type", data.research_type],
    ["Target population", data.target_population],
    ["Scope", data.scope],
  ].filter(([, v]) => typeof v === "string" && v.trim()) as Array<[string, string]>;

  return (
    <div className="space-y-4">
      {title && (
        <div>
          <FieldLabel name="research_title" top />
          <div className="font-serif text-[16px] leading-relaxed text-ink-900 mt-1">{title}</div>
        </div>
      )}
      {scalars.length > 0 && (
        <div className="space-y-1.5">
          {scalars.map(([k, v]) => <KVRich key={k} k={k} v={v} />)}
        </div>
      )}
      {rqs.length > 0 && (
        <div>
          <FieldLabel name={`research_questions (${rqs.length})`} />
          <ol className="list-decimal pl-5 mt-2 text-[13.5px] text-ink-800 leading-relaxed space-y-1.5">
            {rqs.map((q, i) => <li key={i}>{q}</li>)}
          </ol>
        </div>
      )}
      {objectives.length > 0 && (
        <div>
          <FieldLabel name={`objectives (${objectives.length})`} />
          <ol className="list-decimal pl-5 mt-2 text-[13.5px] text-ink-800 leading-relaxed space-y-1.5">
            {objectives.map((o, i) => <li key={i}>{o}</li>)}
          </ol>
        </div>
      )}
    </div>
  );
}

function M2Body({ data }: { data: Record<string, any> | null }) {
  if (!data) return <EmptyHint text="No literature yet — run M2 scout to gather sources." />;
  // Loose shapes: agent + engine wrote these at different times. The current
  // bootstrap/M2 commit shape is `gap_id` + `one_sentence` + `type` +
  // `why_its_a_gap` + `addressable_as`; older paths used `description`/`text`/
  // `title` + `relevance`. Tolerate all so the chip never renders an empty "—".
  type Gap = {
    id?: string; gap_id?: string;
    one_sentence?: string; type?: string;
    // The committed shape uses `why_it_is_a_gap`; an older path had the typo'd
    // `why_its_a_gap`. Tolerate both.
    why_it_is_a_gap?: string; why_its_a_gap?: string; addressable_as?: string;
    description?: string; text?: string; title?: string;
    relevance?: string;
    confirmed?: boolean;
    supporting_papers?: Array<any>;
  };
  type Hypothesis = { id?: string; text?: string; statement?: string; grounded_in?: string };
  type Paper = {
    id?: string; title?: string; authors?: string[] | string;
    author?: string; year?: number | string;
    doi?: string; url?: string; source?: string; venue?: string;
  };
  const gaps = (data.research_gaps || []) as Gap[];
  const hypotheses = (data.hypotheses || []) as (Hypothesis | string)[];
  const sources = (data.citation_list || data.literature_sources || []) as Paper[];

  // Modal state — one selected item at a time. `kind` discriminates the
  // payload shape so the modal can render the right view.
  const [modal, setModal] = useState<
    | { kind: "gap"; index: number }
    | { kind: "hypothesis"; index: number }
    | { kind: "sources" }
    | null
  >(null);

  // Show what the gap actually IS, not its category. `type` ("context gap")
  // is only a classification — surfacing it as the chip text read as nonsense
  // ("gap-1 context gap"). Prefer the real content: a one-sentence summary, the
  // rationale (why_it_is_a_gap), or what it's addressable as. `type` is dropped
  // from the chain (it's shown as a separate label in the gap modal).
  const gapText = (g: Gap) =>
    g.one_sentence || g.why_it_is_a_gap || g.why_its_a_gap || g.addressable_as ||
    g.description || g.text || g.title || "(research gap)";
  // Chip + modal id: the commit shape stores `gap_id` ("1"), older paths used
  // `id`. Fall back to positional G{n} so a malformed gap still gets a label.
  const gapId = (g: Gap, i: number) =>
    g.id ?? (g.gap_id ? `G${g.gap_id}` : `G${i + 1}`);
  const hypothesisText = (h: Hypothesis | string | Record<string, any>): string => {
    if (typeof h === "string") return h;
    // Different commit paths use different keys: design uses `text`,
    // M3 schema migration left some commits as `statement`, the engine
    // sometimes writes `description` or `hypothesis`, and the autodraft
    // path occasionally lands `content` or `body`. Try them all; fall
    // back to em-dash so we never throw.
    return (
      (h as any).text ||
      (h as any).statement ||
      (h as any).description ||
      (h as any).hypothesis ||
      (h as any).content ||
      (h as any).body ||
      (h as any).label ||
      "—"
    );
  };

  return (
    <>
      {gaps.length > 0 && (
        <>
          <FieldLabel name="research_gaps" count={gaps.length} top />
          <div className="flex flex-wrap gap-1.5 mt-1.5">
            {gaps.map((g, i) => (
              <button
                key={i}
                type="button"
                onClick={() => setModal({ kind: "gap", index: i })}
                title={gapText(g)}
                className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md transition-colors hover:bg-primary-50 ${
                  g.confirmed
                    ? "bg-emerald-50 text-emerald-700"
                    : "bg-ink-100 text-ink-600"
                }`}
              >
                <span className="font-serif font-extrabold text-[11px]">
                  {gapId(g, i)}
                </span>
                <span className="text-[11.5px] text-ink-700 max-w-[140px] truncate">
                  {gapText(g)}
                </span>
              </button>
            ))}
          </div>
        </>
      )}

      {hypotheses.length > 0 && (
        <>
          <FieldLabel name="hypotheses" count={hypotheses.length} />
          <ul className="mt-1.5 space-y-1 list-none">
            {hypotheses.map((h, i) => {
              const id = typeof h === "string" ? `H${i + 1}` : (h.id ?? `H${i + 1}`);
              const text = hypothesisText(h);
              return (
                <li key={i}>
                  <button
                    type="button"
                    onClick={() => setModal({ kind: "hypothesis", index: i })}
                    className="w-full text-left text-[12.5px] text-ink-700 px-1.5 py-1 rounded-md hover:bg-primary-50 transition-colors"
                  >
                    <span className="font-bold text-primary-700 mr-1.5">{id}</span>
                    <span className="line-clamp-2">{text}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </>
      )}

      {Array.isArray(sources) && sources.length > 0 && (
        <>
          <FieldLabel name="literature_sources" />
          <button
            type="button"
            onClick={() => setModal({ kind: "sources" })}
            className="w-full text-left flex items-center gap-2.5 mt-1 px-1.5 py-1.5 rounded-md hover:bg-primary-50 transition-colors group"
          >
            <span className="text-[22px] font-extrabold text-ink-900 tabular-nums">
              {sources.length}
            </span>
            <span className="text-[11.5px] text-ink-500 flex-1">
              papers · click to view
            </span>
            <ExternalLink className="w-3.5 h-3.5 text-ink-400 group-hover:text-primary-600" />
          </button>
        </>
      )}

      {gaps.length === 0 && hypotheses.length === 0 && (!Array.isArray(sources) || sources.length === 0) && (
        <EmptyHint text="No M2 data committed yet." />
      )}

      {/* Modal — renders the selected gap / hypothesis / source list with
          full text + structured details. */}
      <SliceModal
        open={modal !== null}
        title={modalTitle(modal, gaps, hypotheses, sources)}
        subtitle={modalSubtitle(modal, gaps, hypotheses, sources)}
        onClose={() => setModal(null)}
      >
        {modal?.kind === "gap" && <GapDetail gap={gaps[modal.index]} />}
        {modal?.kind === "hypothesis" && (
          <HypothesisDetail
            hypothesis={hypotheses[modal.index]}
            text={hypothesisText(hypotheses[modal.index])}
          />
        )}
        {modal?.kind === "sources" && <SourceList papers={sources} />}
      </SliceModal>
    </>
  );
}


function modalTitle(
  m: { kind: "gap"; index: number } | { kind: "hypothesis"; index: number } | { kind: "sources" } | null,
  gaps: any[], hyps: any[], sources: any[],
): string {
  if (!m) return "";
  if (m.kind === "gap") {
    const g = gaps[m.index];
    // Title = the gap's category ("Context gap"), not the bare id ("gap-1").
    // The id moves to the subtitle. Falls back to the id when no type.
    const t = (g?.type as string | undefined)?.trim();
    if (t) return t.charAt(0).toUpperCase() + t.slice(1);
    return g?.id ?? (g?.gap_id ? `G${g.gap_id}` : `Gap ${m.index + 1}`);
  }
  if (m.kind === "hypothesis") {
    const h = hyps[m.index];
    const id = typeof h === "string" ? `H${m.index + 1}` : (h.id ?? `H${m.index + 1}`);
    return id;
  }
  return `Literature sources (${sources.length})`;
}

function modalSubtitle(
  m: { kind: "gap"; index: number } | { kind: "hypothesis"; index: number } | { kind: "sources" } | null,
  _gaps: any[], _hyps: any[], _sources: any[],
): string | undefined {
  if (!m) return undefined;
  if (m.kind === "gap") {
    const g = _gaps[m.index];
    const id = g?.id ?? (g?.gap_id ? `G${g.gap_id}` : null);
    return id ? `Research gap · ${id}` : "Research gap";
  }
  if (m.kind === "hypothesis") return "Hypothesis";
  return "Click any paper to open its source";
}


// --- detail renderers for the modal body ---

function GapDetail({ gap }: { gap: any }) {
  const supporting: any[] = gap?.supporting_papers ?? [];
  // Current commit shape carries `type` + `why_it_is_a_gap` + `addressable_as`
  // (`why_its_a_gap` was a typo'd older key; `relevance` even older). Show
  // whichever are present.
  const gapType = gap?.type;
  const why = gap?.why_it_is_a_gap ?? gap?.why_its_a_gap;
  const addressable = gap?.addressable_as;
  // Only show a standalone headline when there's a distinct one-sentence
  // summary — otherwise `text` is the rationale and would duplicate the "why
  // it's a gap" block below.
  const headline = gap?.one_sentence;
  return (
    <div className="space-y-3">
      {/* `type` is shown as the modal title now — only surface the older
          `relevance` field here (when there's no type). */}
      {!gapType && gap?.relevance && (
        <div className="inline-flex items-center px-2 py-0.5 rounded-full bg-primary-50 text-primary-700 text-[11px] font-semibold">
          Relevance: {gap.relevance}
        </div>
      )}
      {headline && <p className="text-[14px] leading-relaxed text-ink-900">{headline}</p>}
      {why && (
        <div className="border-l-2 border-primary-200 pl-3 text-[12.5px] text-ink-600">
          <FieldLabel name="why it's a gap" top />
          <div className="mt-1">{why}</div>
        </div>
      )}
      {addressable && (
        <div className="border-l-2 border-emerald-200 pl-3 text-[12.5px] text-ink-600">
          <FieldLabel name="how to address it" top />
          <div className="mt-1">{addressable}</div>
        </div>
      )}
      {supporting.length > 0 && (
        <div>
          <FieldLabel name={`supporting papers (${supporting.length})`} top />
          <ul className="mt-2 space-y-1.5">
            {supporting.map((p: any, i: number) => (
              <li key={i}>
                <SourceRow paper={p} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function HypothesisDetail({ hypothesis, text }: { hypothesis: any; text: string }) {
  const grounded = typeof hypothesis === "object" ? hypothesis?.grounded_in : undefined;
  return (
    <div className="space-y-3">
      <p className="text-[14px] leading-relaxed text-ink-900">{text}</p>
      {grounded && (
        <div className="border-l-2 border-primary-200 pl-3 text-[12.5px] text-ink-600">
          <FieldLabel name="grounded in" top />
          <div className="mt-1">{grounded}</div>
        </div>
      )}
    </div>
  );
}

function SourceList({ papers }: { papers: any[] }) {
  if (papers.length === 0) {
    return <EmptyHint text="No sources yet." />;
  }
  return (
    <ul className="space-y-2">
      {papers.map((p, i) => (
        <li key={i}>
          <SourceRow paper={p} />
        </li>
      ))}
    </ul>
  );
}

function SourceRow({ paper }: { paper: any }) {
  // Tolerate different agent/engine field names.
  const authors = Array.isArray(paper.authors)
    ? paper.authors.join(", ")
    : (paper.authors || paper.author || "");
  const year = paper.year ?? paper.published_year;
  const title = paper.title ?? "";
  const venue = paper.venue || paper.source;
  const url = paper.doi ? `https://doi.org/${paper.doi}` : paper.url;
  const page = paper.page;

  // Two shapes ride on the same field in M2 commits:
  //  1. Full paper records from the citation scout — have a `title` (+ usually
  //     authors/year/doi). Renders as a PDF-thumbnail row with the title as
  //     the headline.
  //  2. Compact `supporting_papers` citations from research-gap commits —
  //     just `{author, year, page}`. With no title we'd render a blank row
  //     (as the user just saw). Switch to a single-line in-text style
  //     citation in that case.
  const isCompactCitation = !title && (authors || year);

  if (isCompactCitation) {
    const cite = [
      authors,
      year ? `(${year})` : null,
      page != null ? `p.${page}` : null,
    ].filter(Boolean).join(", ");
    // Compact citations from supporting_papers ({author, year, page}) have
    // no DOI/URL of their own. Build a Google Scholar query from
    // author + year so the row is still clickable — the user can find the
    // paper themselves without having to retype the citation.
    const scholarUrl =
      url ??
      `https://scholar.google.com/scholar?q=${encodeURIComponent(
        [authors, year].filter(Boolean).join(" "),
      )}`;
    return (
      <a
        href={scholarUrl}
        target="_blank"
        rel="noreferrer noopener"
        title={
          url
            ? "Open source"
            : "Search Google Scholar for this citation"
        }
        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md hover:bg-primary-50 transition-colors text-[12.5px] text-ink-700 hover:text-primary-700"
      >
        <span>{cite}</span>
        <ExternalLink className="w-3 h-3" />
      </a>
    );
  }

  const inner = (
    <div className="flex items-start gap-2.5 text-[13px]">
      <span className="shrink-0 mt-0.5 w-[20px] h-[24px] rounded-sm bg-primary-50 border border-ink-200 inline-flex items-end justify-center text-[8px] font-extrabold text-primary-700">
        PDF
      </span>
      <div className="flex-1 min-w-0">
        <div className="font-semibold text-ink-900 leading-snug">{title || "(untitled)"}</div>
        <div className="text-[12px] text-ink-500 mt-0.5">
          {authors || "—"}
          {year && <> · {year}</>}
          {venue && <> · <em>{venue}</em></>}
        </div>
        {paper.doi && (
          <div className="text-[11.5px] text-ink-400 font-mono mt-0.5">doi:{paper.doi}</div>
        )}
      </div>
      {url && <ExternalLink className="w-3.5 h-3.5 text-ink-400 shrink-0 mt-1" />}
    </div>
  );
  return url ? (
    <a
      href={url}
      target="_blank"
      rel="noreferrer noopener"
      className="block px-2.5 py-2 rounded-lg hover:bg-primary-50 transition-colors"
    >
      {inner}
    </a>
  ) : (
    <div className="block px-2.5 py-2">{inner}</div>
  );
}

function M3Body({ data }: { data: Record<string, any> | null }) {
  // Modal state for click-to-show on the rich M3 fields.
  const [modal, setModal] = useState<
    | { kind: "methodology" }
    | { kind: "conceptual_model" }
    | { kind: "hypotheses"; index: number | null }
    | { kind: "instrument" }
    | null
  >(null);

  if (!data) return <EmptyHint text="No methodology set yet — open M3 to design." />;

  const meth = data.methodology;
  const conceptualModel = data.conceptual_model as { nodes?: any[]; edges?: any[] } | undefined;
  const hypotheses = (data.hypotheses || []) as Array<{ id?: string; text?: string; statement?: string }>;
  const questionnaire = data.questionnaire_text as string | undefined;
  const sampling = meth?.sampling || {};

  if (!meth && !conceptualModel && hypotheses.length === 0 && !questionnaire) {
    return <EmptyHint text="No M3 data committed yet." />;
  }

  return (
    <>
      {meth && (
        <>
          <button
            type="button"
            onClick={() => setModal({ kind: "methodology" })}
            className="block w-full text-left -mx-1 px-1 py-0.5 rounded-md hover:bg-primary-50 transition-colors group"
          >
            <FieldLabel name="methodology" top />
          </button>
          <div className="mt-1.5 space-y-1.5">
            {meth.paradigm && <KV k="Paradigm" v={meth.paradigm} />}
            {meth.design && <KV k="Design" v={meth.design} />}
            {meth.tool && <KV k="Tool" v={meth.tool} />}
            {(sampling.minSize || sampling.targetSize || meth.target_sample_size) && (
              <KV
                k="Sample"
                v={`n ≥ ${sampling.minSize ?? meth.target_sample_size ?? "?"}${
                  sampling.targetSize ? ` (target ${sampling.targetSize})` : ""
                }`}
              />
            )}
          </div>
        </>
      )}

      {conceptualModel && (conceptualModel.nodes?.length || conceptualModel.edges?.length) ? (
        <ClickRow
          name="conceptual_model"
          summary={`${conceptualModel.nodes?.length ?? 0} constructs · ${conceptualModel.edges?.length ?? 0} edges`}
          onClick={() => setModal({ kind: "conceptual_model" })}
        />
      ) : null}

      {hypotheses.length > 0 && (
        <>
          <button
            type="button"
            onClick={() => setModal({ kind: "hypotheses", index: null })}
            className="block w-full text-left -mx-1 px-1 py-0.5 rounded-md hover:bg-primary-50 transition-colors group"
          >
            <FieldLabel name="hypotheses" count={hypotheses.length} />
          </button>
          <ul className="mt-1.5 space-y-1 list-none">
            {hypotheses.slice(0, 3).map((h, i) => (
              <li key={i}>
                <button
                  type="button"
                  onClick={() => setModal({ kind: "hypotheses", index: i })}
                  className="w-full text-left text-[12.5px] text-ink-700 px-1.5 py-1 rounded-md hover:bg-primary-50 transition-colors"
                >
                  <span className="font-bold text-primary-700 mr-1.5">
                    {h.id ?? `H${i + 1}`}
                  </span>
                  <span className="line-clamp-1">
                    {readHypothesisText(h)}
                  </span>
                </button>
              </li>
            ))}
            {hypotheses.length > 3 && (
              <li>
                <button
                  type="button"
                  onClick={() => setModal({ kind: "hypotheses", index: null })}
                  className="text-[11.5px] text-primary-600 px-1.5 hover:underline"
                >
                  +{hypotheses.length - 3} more…
                </button>
              </li>
            )}
          </ul>
        </>
      )}

      {questionnaire && (
        <ClickRow
          name="questionnaire_text"
          summary={`${questionnaire.split(/\s+/).length} words · click to view`}
          onClick={() => setModal({ kind: "instrument" })}
        />
      )}

      {data.needs_review_note && (
        <div className="mt-2.5 px-2.5 py-2 rounded-lg bg-amber-50 text-amber-800 text-[11.5px] leading-snug font-semibold">
          ⚠ {data.needs_review_note}
        </div>
      )}

      {/* Detail modal */}
      <SliceModal
        open={modal !== null}
        title={m3ModalTitle(modal, hypotheses)}
        subtitle={m3ModalSubtitle(modal)}
        onClose={() => setModal(null)}
      >
        {modal?.kind === "methodology" && <MethodologyDetail meth={meth} sampling={sampling} />}
        {modal?.kind === "conceptual_model" && <ConceptualModelDetail model={conceptualModel} />}
        {modal?.kind === "hypotheses" && (
          modal.index === null ? <HypothesesList hypotheses={hypotheses} />
            : <HypothesisDetail
                hypothesis={hypotheses[modal.index]}
                text={readHypothesisText(hypotheses[modal.index])}
              />
        )}
        {modal?.kind === "instrument" && <InstrumentDetail text={questionnaire ?? ""} />}
      </SliceModal>
    </>
  );
}


// --- M3 modal helpers ---

function m3ModalTitle(
  m:
    | { kind: "methodology" }
    | { kind: "conceptual_model" }
    | { kind: "hypotheses"; index: number | null }
    | { kind: "instrument" }
    | null,
  hypotheses: Array<{ id?: string; text?: string; statement?: string }>,
): string {
  if (!m) return "";
  switch (m.kind) {
    case "methodology":      return "Methodology";
    case "conceptual_model": return "Conceptual model";
    case "hypotheses":
      if (m.index === null) return `Hypotheses (${hypotheses.length})`;
      return hypotheses[m.index]?.id ?? `H${m.index + 1}`;
    case "instrument":       return "Questionnaire";
  }
}

function m3ModalSubtitle(
  m:
    | { kind: "methodology" }
    | { kind: "conceptual_model" }
    | { kind: "hypotheses"; index: number | null }
    | { kind: "instrument" }
    | null,
): string | undefined {
  if (!m) return undefined;
  switch (m.kind) {
    case "methodology":      return "Design · sampling · analysis";
    case "conceptual_model": return "Constructs and hypothesis paths";
    case "hypotheses":       return m.index === null ? "All committed hypotheses" : "Hypothesis";
    case "instrument":       return "Full questionnaire text";
  }
}


function ClickRow({
  name, summary, onClick,
}: {
  name: string;
  summary: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full flex items-center justify-between gap-2 mt-3 px-2 py-1.5 -mx-1 rounded-md hover:bg-primary-50 transition-colors group"
    >
      <div className="flex flex-col items-start min-w-0">
        <span className="text-[11px] uppercase tracking-[0.05em] text-ink-500 font-semibold">
          {name}
        </span>
        <span className="text-[12px] text-ink-600 mt-0.5 truncate">{summary}</span>
      </div>
      <ExternalLink className="w-3.5 h-3.5 text-ink-400 group-hover:text-primary-600 shrink-0" />
    </button>
  );
}


// --- M3 detail renderers ---

function MethodologyDetail({ meth, sampling }: { meth: any; sampling: any }) {
  return (
    <div className="space-y-3 text-[13.5px]">
      {meth.paradigm && <KVRich k="Paradigm" v={meth.paradigm} />}
      {meth.design && <KVRich k="Design" v={meth.design} />}
      {meth.tool && <KVRich k="Tool" v={meth.tool} />}
      {meth.sampling_strategy && <KVRich k="Sampling strategy" v={meth.sampling_strategy} />}
      {(meth.target_sample_size || sampling.minSize || sampling.targetSize) && (
        <KVRich
          k="Target sample"
          v={
            meth.target_sample_size
              ? `n ≥ ${meth.target_sample_size}`
              : `n ≥ ${sampling.minSize ?? "?"}${
                  sampling.targetSize ? ` (target ${sampling.targetSize})` : ""
                }`
          }
        />
      )}
      {meth.mixed_design_type && (
        <KVRich k="Mixed design" v={meth.mixed_design_type} />
      )}
    </div>
  );
}

// Build a Mermaid `flowchart LR` from the model's nodes + edges so the
// conceptual model renders as an actual diagram (boxes + hypothesis arrows)
// instead of only two text lists. Tolerant of both edge shapes the codebase
// emits: design's {from,to,label} and the schema's {source,target,hypothesis}.
function _mermaidId(raw: unknown, fallback: string): string {
  const s = String(raw ?? "").trim();
  // Mermaid node ids must be token-safe — keep alnum/underscore, collapse rest.
  const id = s.replace(/[^A-Za-z0-9_]/g, "_").replace(/^_+|_+$/g, "");
  return id || fallback;
}

function _mermaidLabel(s: unknown): string {
  // Quotes/pipes/newlines break Mermaid label syntax — neutralize them.
  return String(s ?? "").replace(/"/g, "'").replace(/\|/g, "/").replace(/\s*\n\s*/g, " ").trim();
}

function _conceptualMermaid(nodes: any[], edges: any[]): string | null {
  const lines = ["flowchart LR"];
  const ids = new Map<string, string>(); // original key -> safe id
  nodes.forEach((n, i) => {
    const key = String(n.id ?? n.label ?? `N${i + 1}`);
    const safe = _mermaidId(n.id ?? n.label, `N${i + 1}`);
    ids.set(key, safe);
    // Also map by label so edges referencing either id or label resolve.
    if (n.label) ids.set(String(n.label), safe);
    const label = _mermaidLabel(n.label ?? n.id ?? key) || key;
    lines.push(`  ${safe}["${label}"]`);
  });
  let drewEdge = false;
  edges.forEach(e => {
    const srcKey = String(e.from ?? e.source ?? "");
    const tgtKey = String(e.to ?? e.target ?? "");
    const src = ids.get(srcKey) || (srcKey ? _mermaidId(srcKey, "") : "");
    const tgt = ids.get(tgtKey) || (tgtKey ? _mermaidId(tgtKey, "") : "");
    if (!src || !tgt) return;
    // Prefer a clean hypothesis id; else strip a redundant "X → Y" prefix the
    // design encodes in the label (the arrow itself already shows direction).
    let lbl = e.hypothesis
      ? String(e.hypothesis)
      : String(e.label ?? "").replace(/^\s*\S+\s*(?:→|->)\s*\S+\s*:?\s*/, "");
    lbl = _mermaidLabel(lbl);
    lines.push(lbl ? `  ${src} -->|"${lbl}"| ${tgt}` : `  ${src} --> ${tgt}`);
    drewEdge = true;
  });
  // Only worth a diagram when there's at least one connection to show.
  return drewEdge ? lines.join("\n") : null;
}

function ConceptualModelDetail({ model }: { model: { nodes?: any[]; edges?: any[] } | undefined }) {
  const nodes = model?.nodes ?? [];
  const edges = model?.edges ?? [];
  const diagram = _conceptualMermaid(nodes, edges);
  return (
    <div className="space-y-4">
      {diagram && (
        <div className="rounded-xl border border-ink-200 bg-white p-3 overflow-x-auto">
          <Mermaid source={diagram} />
        </div>
      )}
      {nodes.length > 0 && (
        <div>
          <FieldLabel name={`constructs (${nodes.length})`} top />
          <ul className="mt-2 space-y-2">
            {nodes.map((n: any, i: number) => (
              <li key={i} className="border border-ink-200 rounded-lg px-3 py-2">
                <div className="flex items-center gap-2">
                  <span className="font-serif font-extrabold text-[11.5px] px-1.5 py-0.5 rounded bg-primary-50 text-primary-700">
                    {n.id ?? `N${i + 1}`}
                  </span>
                  <span className="text-[13.5px] font-semibold text-ink-900">{n.label ?? "—"}</span>
                  {n.type && (
                    <span className="text-[11px] uppercase tracking-[0.04em] text-ink-500 font-semibold ml-auto">
                      {n.type}
                    </span>
                  )}
                </div>
                {Array.isArray(n.questions) && n.questions.length > 0 && (
                  <ol className="list-decimal pl-5 mt-2 text-[12.5px] text-ink-700 space-y-0.5">
                    {n.questions.map((q: string, j: number) => <li key={j}>{q}</li>)}
                  </ol>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      {edges.length > 0 && (
        <div>
          <FieldLabel name={`hypothesis paths (${edges.length})`} />
          <ul className="mt-2 space-y-1.5">
            {edges.map((e: any, i: number) => {
              // Two shapes coexist: design's `{from, to, label}` (where
              // label carries the full "SMU → SA: −" string) and the
              // schema's `{source, target, hypothesis, effect_type}`. We
              // try both keys, and only render the X → Y prefix when we
              // actually have a clean construct pair AND the label
              // doesn't already include an arrow.
              const src: string | undefined = e.from ?? e.source;
              const tgt: string | undefined = e.to ?? e.target;
              const label: string | undefined = e.label;
              const labelHasArrow = !!label && /[→\->]/.test(label);
              const showPathPrefix = src && tgt && !labelHasArrow;
              return (
                <li key={i} className="text-[13px] flex items-center gap-2">
                  {showPathPrefix && (
                    <span className="font-mono text-ink-500 text-[12.5px]">
                      {src} → {tgt}
                    </span>
                  )}
                  {e.hypothesis && (
                    <span className="px-1.5 py-0.5 rounded bg-primary-50 text-primary-700 font-bold text-[11.5px]">
                      {e.hypothesis}
                    </span>
                  )}
                  {e.effect_type && (
                    <span
                      className={`text-[11.5px] font-semibold ${
                        e.effect_type === "positive" ? "text-emerald-700" : "text-amber-700"
                      }`}
                    >
                      {e.effect_type === "positive" ? "+" : "−"}
                    </span>
                  )}
                  {label && <span className="text-ink-700">{label}</span>}
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {nodes.length === 0 && edges.length === 0 && (
        <EmptyHint text="No conceptual-model graph committed yet." />
      )}
    </div>
  );
}

function HypothesesList({ hypotheses }: { hypotheses: Array<Record<string, any>> }) {
  return (
    <ul className="space-y-3">
      {hypotheses.map((h, i) => (
        <li key={i}>
          <div className="font-bold text-primary-700 text-[13px]">
            {h.id ?? `H${i + 1}`}
          </div>
          <div className="text-[13.5px] text-ink-900 leading-relaxed mt-0.5">
            {readHypothesisText(h)}
          </div>
        </li>
      ))}
    </ul>
  );
}

// Same precedence ladder as the M2 reader. Kept as a top-level helper so
// both the M3 modal and the M3 inline preview show the same value.
function readHypothesisText(h: any): string {
  if (typeof h === "string") return h;
  return (
    h?.text ||
    h?.statement ||
    h?.description ||
    h?.hypothesis ||
    h?.content ||
    h?.body ||
    h?.label ||
    "—"
  );
}

function InstrumentDetail({ text }: { text: string }) {
  if (!text.trim()) {
    return <EmptyHint text="Questionnaire is empty." />;
  }
  return (
    <pre className="whitespace-pre-wrap font-serif text-[13.5px] leading-relaxed text-ink-900">
      {text}
    </pre>
  );
}

function KVRich({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex gap-3 items-baseline">
      <span className="min-w-[120px] text-[11px] uppercase tracking-[0.05em] text-ink-500 font-semibold">
        {k}
      </span>
      <span className="flex-1 text-ink-900 font-medium">{v}</span>
    </div>
  );
}


function EmptyHint({ text }: { text: string }) {
  return <div className="text-[12.5px] text-ink-500 leading-snug">{text}</div>;
}

// `truncate` used to be called by M2Body before gaps moved into a modal —
// kept here in case other section bodies want it back.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function truncate(s: string, n: number): string {
  if (s.length <= n) return s;
  return s.slice(0, n).trimEnd() + "…";
}
