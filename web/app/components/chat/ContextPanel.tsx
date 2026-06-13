"use client";

import { useState } from "react";
import { AlertTriangle, Clock, Coins, Download, ExternalLink, FileText } from "lucide-react";

import { SliceModal } from "./SliceModal";
import { mintStreamToken } from "@/app/lib/api";


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
  contextStore,
  uploads,
  currentModule,
  moduleStatus,
  threadCredits,
}: {
  contextStore: ContextStore;
  uploads: UploadItem[];
  currentModule?: string;
  moduleStatus?: ModuleStatusMap;
  /** Total credits spent in the current thread — shown in the header. */
  threadCredits?: number;
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
            <CtxSection
              label="M1 · Topic & questions"
              status={sectionStatus("M1", contextStore.m1_topic)}
            >
              <M1Body data={contextStore.m1_topic} />
            </CtxSection>

            <CtxSection
              label="M2 · Gaps & hypotheses"
              status={sectionStatus("M2", contextStore.m2_literature)}
            >
              <M2Body data={contextStore.m2_literature} />
            </CtxSection>

            <CtxSection
              label="M3 · Methodology & model"
              status={sectionStatus("M3", contextStore.m3_design)}
            >
              <M3Body data={contextStore.m3_design} />
            </CtxSection>

            <CtxSection
              label="M4 · Analysis"
              status={sectionStatus("M4", contextStore.m4_analysis)}
            >
              <div className="text-[12.5px] text-ink-500 leading-snug">
                Soft-locked — you can ask or start; the agent will prompt if a dependency is missing.
              </div>
            </CtxSection>

            <CtxSection
              label="M5 · Writing"
              status={sectionStatus("M5", contextStore.m5_writing)}
            >
              <M5Body data={contextStore.m5_writing} />
            </CtxSection>

            {uploads.length > 0 && (
              <CtxSection label={`Uploads (${uploads.length})`} status="in_progress">
                <div className="space-y-1">
                  {uploads.slice(0, 5).map(u => (
                    <div key={u.id} className="text-[12.5px] text-ink-700 truncate">
                      📄 {u.filename}
                      {u.page_count && <span className="text-ink-400 ml-1">· {u.page_count}p</span>}
                    </div>
                  ))}
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
  children,
}: {
  label: string;
  status: SectionStatus;
  children: React.ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const dot = STATUS_DOT[status];
  return (
    <div className="border border-ink-200 rounded-xl bg-white">
      <button
        type="button"
        onClick={() => setCollapsed(c => !c)}
        className="w-full px-3.5 pt-3 pb-2 flex items-center gap-2 text-left hover:bg-ink-50/60 transition-colors rounded-t-xl"
      >
        <span className={`w-2 h-2 rounded-full shrink-0 ${dot}`} />
        <span className="text-[12.5px] font-bold text-ink-800">{label}</span>
        <span className="flex-1" />
        {status === "needs_review" && (
          <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
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


// Persisted artifact shape from /m5/export + auto-export hook (agent_state.py).
type ExportArtifact = {
  kind: "docx" | "pdf";
  s3_key: string;
  size_bytes: number;
  download_url: string;
  uri?: string;
};

function M5Body({ data }: { data: Record<string, any> | null }) {
  if (!data) {
    return (
      <EmptyHint text="Writing hasn't started — M5 builds the final docx/pdf from M1–M4 once those are done." />
    );
  }
  const artifacts = (data.export_artifacts || []) as ExportArtifact[];
  const chapters = (data.chapters || {}) as Record<string, unknown>;
  const chapterCount = Object.keys(chapters).length;
  const finalSections = Array.isArray(data.final_sections) ? data.final_sections : [];
  return (
    <>
      {chapterCount > 0 && (
        <>
          <FieldLabel name="chapters" count={chapterCount} top />
          <div className="text-[12.5px] text-ink-600 mt-1">
            {chapterCount}/6 chapters drafted
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
      <FieldLabel name="exports" top={chapterCount === 0 && finalSections.length === 0} />
      {artifacts.length > 0 ? (
        <div className="mt-1.5 space-y-1.5">
          {artifacts.map(a => (
            <ExportArtifactRow key={a.s3_key} artifact={a} />
          ))}
        </div>
      ) : (
        <div className="text-[12.5px] text-ink-500 mt-1 leading-snug">
          No export yet — runs automatically when M5 is marked done.
        </div>
      )}
    </>
  );
}

function ExportArtifactRow({ artifact }: { artifact: ExportArtifact }) {
  const label = artifact.kind.toUpperCase();
  const size =
    artifact.size_bytes >= 1024 * 1024
      ? `${(artifact.size_bytes / (1024 * 1024)).toFixed(1)} MB`
      : `${(artifact.size_bytes / 1024).toFixed(0)} KB`;
  // The /exports/{filename} route 302s to a signed S3 URL — auth still
  // required. Browsers can't POST for a file download (and keep the filename
  // headers), so instead of putting the long-lived JWT in the URL we mint a
  // short-lived, scoped stream token on click and navigate with ?st=. Keeps
  // the JWT out of access logs / referrers.
  const apiBase = process.env.NEXT_PUBLIC_API_BASE || "";
  const url = artifact.download_url.startsWith("/api/v1/")
    ? `${apiBase}${artifact.download_url.replace(/^\/api\/v1/, "")}`
    : artifact.download_url;
  const onDownload = async (e: React.MouseEvent) => {
    e.preventDefault();
    const m = artifact.download_url.match(/\/projects\/([^/]+)\/exports\/([^/?]+)/);
    if (!m) return;
    const st = await mintStreamToken(`project-export:${m[1]}/${m[2]}`);
    const sep = url.includes("?") ? "&" : "?";
    window.location.href = `${url}${sep}st=${encodeURIComponent(st)}`;
  };
  return (
    <a
      href={url}
      download
      onClick={onDownload}
      className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg border border-ink-200 bg-white hover:border-primary-300 hover:bg-primary-50 transition-colors group"
    >
      <FileText className="w-3.5 h-3.5 text-primary-600 shrink-0" aria-hidden />
      <span className="font-serif text-[12.5px] font-extrabold text-ink-900">
        {label}
      </span>
      <span className="text-[11.5px] text-ink-500">· {size}</span>
      <Download className="w-3.5 h-3.5 text-ink-400 group-hover:text-primary-600 ml-auto shrink-0" aria-hidden />
    </a>
  );
}

function M1Body({ data }: { data: Record<string, any> | null }) {
  if (!data) return <EmptyHint text="Topic not set yet — start in M1." />;
  const title = data.research_title;
  const rqs = (data.research_questions || []) as string[];
  return (
    <>
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
      {!title && rqs.length === 0 && <EmptyHint text="No M1 data committed yet." />}
    </>
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
    why_its_a_gap?: string; addressable_as?: string;
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

  const gapText = (g: Gap) =>
    g.one_sentence || g.description || g.text || g.title || g.type || "—";
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
        {modal?.kind === "gap" && <GapDetail gap={gaps[modal.index]} text={gapText(gaps[modal.index])} />}
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
  if (m.kind === "gap") return "Research gap";
  if (m.kind === "hypothesis") return "Hypothesis";
  return "Click any paper to open its source";
}


// --- detail renderers for the modal body ---

function GapDetail({ gap, text }: { gap: any; text: string }) {
  const supporting: any[] = gap?.supporting_papers ?? [];
  // Current commit shape carries `type` + `why_its_a_gap` + `addressable_as`;
  // `relevance` was the older field. Show whichever are present.
  const gapType = gap?.type;
  const why = gap?.why_its_a_gap;
  const addressable = gap?.addressable_as;
  return (
    <div className="space-y-3">
      {(gapType || gap?.relevance) && (
        <div className="inline-flex items-center px-2 py-0.5 rounded-full bg-primary-50 text-primary-700 text-[11px] font-semibold">
          {gapType ?? `Relevance: ${gap.relevance}`}
        </div>
      )}
      <p className="text-[14px] leading-relaxed text-ink-900">{text}</p>
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
    | { kind: "themes" }
    | { kind: "interview_guide" }
    | null
  >(null);

  if (!data) return <EmptyHint text="No methodology set yet — open M3 to design." />;

  const meth = data.methodology;
  const conceptualModel = data.conceptual_model as { nodes?: any[]; edges?: any[] } | undefined;
  const hypotheses = (data.hypotheses || []) as Array<{ id?: string; text?: string; statement?: string }>;
  const questionnaire = data.questionnaire_text as string | undefined;
  const themes = (data.themes || []) as any[];
  const interviewGuide = data.interview_guide as Record<string, any> | undefined;
  const sampling = meth?.sampling || {};

  if (!meth && !conceptualModel && hypotheses.length === 0 && !questionnaire && themes.length === 0 && !interviewGuide) {
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

      {themes.length > 0 && (
        <ClickRow
          name="themes"
          summary={`${themes.length} themes`}
          onClick={() => setModal({ kind: "themes" })}
        />
      )}

      {interviewGuide && (
        <ClickRow
          name="interview_guide"
          summary={`${Object.keys(interviewGuide.questions ?? interviewGuide).length || 0} items`}
          onClick={() => setModal({ kind: "interview_guide" })}
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
        {modal?.kind === "themes" && <ThemesDetail themes={themes} />}
        {modal?.kind === "interview_guide" && <InterviewGuideDetail guide={interviewGuide!} />}
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
    | { kind: "themes" }
    | { kind: "interview_guide" }
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
    case "themes":           return "Themes";
    case "interview_guide":  return "Interview guide";
  }
}

function m3ModalSubtitle(
  m:
    | { kind: "methodology" }
    | { kind: "conceptual_model" }
    | { kind: "hypotheses"; index: number | null }
    | { kind: "instrument" }
    | { kind: "themes" }
    | { kind: "interview_guide" }
    | null,
): string | undefined {
  if (!m) return undefined;
  switch (m.kind) {
    case "methodology":      return "Paradigm · design · sampling · tool";
    case "conceptual_model": return "Constructs and hypothesis paths";
    case "hypotheses":       return m.index === null ? "All committed hypotheses" : "Hypothesis";
    case "instrument":       return "Full questionnaire text";
    case "themes":           return "Qualitative themes";
    case "interview_guide":  return "Interview / focus-group guide";
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

function ConceptualModelDetail({ model }: { model: { nodes?: any[]; edges?: any[] } | undefined }) {
  const nodes = model?.nodes ?? [];
  const edges = model?.edges ?? [];
  return (
    <div className="space-y-4">
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

function ThemesDetail({ themes }: { themes: any[] }) {
  return (
    <ul className="space-y-3">
      {themes.map((t, i) => (
        <li key={i}>
          <div className="font-bold text-primary-700 text-[13px]">
            {t.id ?? t.name ?? `T${i + 1}`}
          </div>
          <div className="text-[13.5px] text-ink-900 leading-relaxed mt-0.5">
            {t.description ?? t.text ?? "—"}
          </div>
        </li>
      ))}
    </ul>
  );
}

function InterviewGuideDetail({ guide }: { guide: Record<string, any> }) {
  // Loose shape: agent commits could be { questions: [...] } or
  // { sections: [{title, questions: [...]}] } or flat string list.
  const questions: string[] = guide.questions ?? guide.items ?? [];
  const sections: Array<{ title?: string; questions?: string[] }> = guide.sections ?? [];
  if (sections.length > 0) {
    return (
      <div className="space-y-4">
        {sections.map((s, i) => (
          <div key={i}>
            {s.title && (
              <div className="font-bold text-ink-900 text-[13.5px] mb-1.5">{s.title}</div>
            )}
            <ol className="list-decimal pl-5 space-y-1 text-[13.5px] text-ink-700">
              {(s.questions ?? []).map((q, j) => <li key={j}>{q}</li>)}
            </ol>
          </div>
        ))}
      </div>
    );
  }
  if (questions.length > 0) {
    return (
      <ol className="list-decimal pl-5 space-y-1.5 text-[13.5px] text-ink-700">
        {questions.map((q, i) => <li key={i}>{q}</li>)}
      </ol>
    );
  }
  return (
    <pre className="whitespace-pre-wrap font-mono text-[12.5px] text-ink-700 bg-ink-50 rounded-lg p-3">
      {JSON.stringify(guide, null, 2)}
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
