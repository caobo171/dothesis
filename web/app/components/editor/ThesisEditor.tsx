"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { type Editor } from "@tiptap/react";
import useSWR, { mutate as revalidate } from "swr";
import { Check, ChevronLeft, ChevronRight, Loader2, X } from "lucide-react";

import { apiFetch } from "@/app/lib/api";
import { tokenStore } from "@/app/lib/tokenStore";

import { OutlineRail, CHAPTER_ORDER, type ChapterName } from "./OutlineRail";
import { ChapterEditor } from "./ChapterEditor";
import { EditorToolbar, FONT_FAMILIES } from "./EditorToolbar";
import { EditorSidePanel } from "./EditorSidePanel";
import type { ClaimAcceptedChapter, ClaimReview, ClaimSuggestion } from "./ClaimConfidencePanel";
import { DocumentToc } from "./DocumentToc";
import { ReExportBar, type ExportArtifact } from "./ReExportBar";
import { SaveBar } from "./SaveBar";
import { UnsavedDiff, type ChapterChange } from "./UnsavedDiff";
import { useThesisSave } from "./hooks/useThesisSave";
import { EmptyState } from "./EmptyState";
import { EditorSkeleton } from "./EditorSkeleton";


// POST-only read: the key is already an absolute /api/v1/… path, so we POST
// directly and fold the access_token into the JSON body — JWT stays out of the
// URL.
const fetcher = (url: string) =>
  fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ access_token: tokenStore.get() }),
  }).then(r => r.json());


type ChapterDict = Record<string, {
  name: string;
  prose: string;
  media?: Array<{ source: string; preview_url: string }>;
  renderable_tokens?: string[];
  document_fingerprint?: string;
  pending_edits: Array<{
    id: string;
    source: "paraphrase" | "translate" | "cite" | "chat_rewrite" | "proofread" | "improve" | "humanize" | "expand" | "shorten";
    old_text: string;
    new_text: string;
    from_offset: number;
    to_offset: number;
    metadata?: { explanation?: string; processing_ms?: number; target_lang?: string; reference_id?: string; style?: string; document_fingerprint?: string };
  }>;
}>;


function _toPendingEdits(raw: ChapterDict[string]["pending_edits"]) {
  // Auto-composed chapters (and any chapter that's never had a chat edit) may
  // omit pending_edits entirely — guard against undefined so the editor renders.
  return (raw ?? []).map(e => ({
    id: e.id,
    source: e.source,
    oldText: e.old_text,
    newText: e.new_text,
    from_offset: e.from_offset,
    to_offset: e.to_offset,
    explanation: e.metadata?.explanation,
    processingMs: e.metadata?.processing_ms,
    metadata: e.metadata,
  }));
}


// Top-level editor surface. Owns chapter selection state, edits-since-export
// counter, and orchestrates re-export. Per-chapter logic (save, AiPending,
// selection toolbar) lives inside ChapterEditor.
// Stable anchor id for a chapter section, so the outline can scroll to it.
const chapterAnchor = (name: string) => `ch-${name}`;


function _headingContents(chapters: ChapterDict) {
  const items: Array<{ chapter: ChapterName; level: number; text: string; index: number }> = [];
  CHAPTER_ORDER.forEach(({ name }) => {
    const prose = chapters[name]?.prose ?? "";
    let index = 0;
    for (const line of prose.split(/\r?\n/)) {
      const match = /^(#{1,4})\s+(.+?)\s*$/.exec(line);
      if (!match) continue;
      // Remove the lightweight inline Markdown that would otherwise show up
      // in the navigation label. The editor heading itself remains untouched.
      const text = match[2]
        .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
        .replace(/[*_`~]/g, "")
        .trim();
      if (text) items.push({ chapter: name, level: match[1].length, text, index });
      index += 1;
    }
  });
  return items;
}


// Spacing lives with the font because it is the same kind of thing: a whole-
// document display choice the markdown cannot carry. A stored setting from
// before spacing existed has neither key, hence the ?? at every read.
const _DEFAULT_LAYOUT = {
  family: FONT_FAMILIES[0].value, size: 16, lineHeight: 1.75, paraGap: 14,
};


export function ThesisEditor({ projectId, onBackToChat }: { projectId: string; onBackToChat?: () => void }) {
  const url = `/api/v1/projects/${projectId}/m5/chapters`;
  const { data: chapters, mutate } = useSWR<ChapterDict>(url, fetcher);
  const { data: projectMeta } = useSWR<{
    name?: string;
    context_store?: { m1_topic?: { research_title?: string } | null };
  }>(`/api/v1/projects/${projectId}`, fetcher);
  const { data: latestClaimReview } = useSWR<{ review?: ClaimReview | null }>(
    `/api/v1/projects/${projectId}/m5/claims/latest`, fetcher,
  );
  const [liveProse, setLiveProse] = useState<Record<string, string>>({});
  const [active, setActive] = useState<ChapterName>("intro");
  const [lastExportAt, setLastExportAt] = useState<Date | null>(null);
  const [editsSinceExport, setEditsSinceExport] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<Error | null>(null);

  // The one shared toolbar binds to whichever chapter editor currently has the
  // caret; each ChapterEditor reports itself via onActiveEditor.
  const [activeEditor, setActiveEditor] = useState<Editor | null>(null);
  // Reference id of the citation the user last clicked — highlights it in the
  // SourcesRail so a citation acts as a jump-to-source.
  const [highlightedSource, setHighlightedSource] = useState<string | null>(null);
  const [claimUpdates, setClaimUpdates] = useState<Record<string, ClaimAcceptedChapter>>({});
  const [claimReview, setClaimReview] = useState<ClaimReview | null>(null);
  const [claimReviewOpen, setClaimReviewOpen] = useState(false);
  const [claimCursor, setClaimCursor] = useState(0);
  const [claimBulkBusy, setClaimBulkBusy] = useState<"accept" | "reject" | null>(null);
  const [claimActionError, setClaimActionError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Document-level font, persisted per project so the choice survives a reload
  // and applies across every stacked chapter. NOT a TipTap mark: chapters are
  // stored as clean markdown (html:false), so a font mark would be dropped on
  // the next save — a whole-document setting is lossless and how a thesis is
  // actually styled. Read lazily to avoid an SSR/client mismatch.
  const fontKey = `dothesis_editor_font_${projectId}`;
  const [font, setFont] = useState<{
    family: string; size: number; lineHeight?: number; paraGap?: number;
  }>(() => {
    if (typeof window === "undefined") return _DEFAULT_LAYOUT;
    try {
      const raw = window.localStorage.getItem(fontKey);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (typeof parsed?.family === "string" && Number.isFinite(parsed?.size)) return parsed;
      }
    } catch { /* corrupt value — fall through to the default */ }
    return _DEFAULT_LAYOUT;
  });
  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(fontKey, JSON.stringify(font));
  }, [fontKey, font]);

  // Outline click → smooth-scroll the chapter section into view.
  const scrollToChapter = useCallback((name: ChapterName) => {
    setActive(name);
    document.getElementById(chapterAnchor(name))?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);
  const scrollToHeading = useCallback((name: ChapterName, index: number) => {
    setActive(name);
    const section = document.getElementById(chapterAnchor(name));
    const heading = section?.querySelectorAll("h1, h2, h3, h4").item(index) as HTMLElement | null;
    (heading ?? section)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  // One save for the whole thesis. Per-chapter state put five "Unsaved
  // changes · Save" bars down a page the student reads as one document, and
  // none of them could answer the only question they have: is my thesis saved?
  const thesisSave = useThesisSave({ projectId });
  const trackProse = useCallback((name: string, prose: string) => {
    thesisSave.track(name, prose);
    // Feeds the document TOC immediately when a heading is renamed. The TOC is
    // derived, never stored, so it cannot drift from unsaved editor content.
    setLiveProse(current => current[name] === prose ? current : { ...current, [name]: prose });
    setEditsSinceExport(n => n + 1);
  }, [thesisSave]);

  const [artifacts, setArtifacts] = useState<ExportArtifact[]>([]);
  // null = closed. Snapshotted on open so the list cannot shift under the
  // reader while they are looking at it.
  const [changes, setChanges] = useState<ChapterChange[] | null>(null);

  const handleReExport = useCallback(async () => {
    setExporting(true);
    setExportError(null);
    try {
      // Save FIRST. The export renders the chapters the SERVER holds, so
      // exporting while dirty silently produced a document without the edits
      // the student had just made and was looking at.
      await thesisSave.save();
      // apiFetch injects access_token + throws ApiError on non-2xx; replaces
      // the bare fetch that used to rely on the dothesis_session cookie.
      // The response is {docx, pdf} — it used to be thrown away, so the button
      // ran, said nothing, and produced no file the student could reach.
      const out = (await apiFetch(
        `/projects/${projectId}/m5/export`, { method: "POST" },
      )) as { docx?: ExportArtifact; pdf?: ExportArtifact } | null;
      setArtifacts([out?.docx, out?.pdf].filter(Boolean) as ExportArtifact[]);
      setLastExportAt(new Date());
      setEditsSinceExport(0);
    } catch (e: any) {
      setExportError(e);
    } finally {
      setExporting(false);
    }
  }, [projectId, thesisSave]);

  const onPendingMutate = useCallback(() => { void mutate(); }, [mutate]);
  const onClaimAccepted = useCallback((update: ClaimAcceptedChapter) => {
    // Let the mounted chapter decide whether it can safely adopt this server
    // revision. SWR then revalidates side data/pending anchors without remounting
    // TipTap over any words typed while the acceptance was in flight.
    setClaimUpdates(current => ({ ...current, [update.chapterName]: update }));
    // Accepted citations change both the export and the source library.
    setEditsSinceExport(current => current + 1);
    void revalidate(`/api/v1/projects/${projectId}/m5/references`);
    void mutate();
  }, [mutate, projectId]);
  useEffect(() => {
    if (latestClaimReview && "review" in latestClaimReview) setClaimReview(latestClaimReview.review ?? null);
  }, [latestClaimReview]);

  const decideClaimInline = useCallback(async (suggestion: ClaimSuggestion, action: "accept" | "reject") => {
    if (!claimReview) return;
    // The endpoint validates the anchor fingerprint. Flush first so an inline
    // action cannot race unsaved editor prose and land on a shifted sentence.
    await thesisSave.save();
    const response = await apiFetch(
      `/projects/${projectId}/m5/claims/${claimReview.review_id}/suggestions/${suggestion.id}/${action}`,
      { method: "POST" },
    ) as { review?: ClaimReview; chapter_name?: ChapterName; chapter?: { prose?: string; document_fingerprint?: string } };
    if (response.review) setClaimReview(response.review);
    if (action === "accept" && response.chapter_name && typeof response.chapter?.prose === "string") {
      onClaimAccepted({ revision: `${suggestion.id}:${Date.now()}`, chapterName: response.chapter_name,
        prose: response.chapter.prose, documentFingerprint: response.chapter.document_fingerprint });
    }
  }, [claimReview, onClaimAccepted, projectId, thesisSave]);

  const decideClaimsBulk = useCallback(async (action: "accept" | "reject") => {
    if (!claimReview || claimBulkBusy) return;
    const items = claimReview.suggestions.filter(item => item.status === "pending" && item.actionable && (action === "reject" || Boolean(item.proposed_text)));
    if (!items.length) return;
    setClaimBulkBusy(action);
    setClaimActionError(null);
    try {
      // Decision: save once, then keep the server's sequential rebase contract.
      // Parallel accepts would all target the same old offsets and corrupt or
      // stale later suggestions in the same chapter.
      await thesisSave.save();
      let latestReview = claimReview;
      for (const item of items) {
        const latestItem = latestReview.suggestions.find(candidate => candidate.id === item.id);
        // An earlier acceptance can intentionally stale an overlapping anchor.
        // Skip it rather than turning a safe bulk run into a 409 halfway through.
        if (!latestItem || latestItem.status !== "pending" || !latestItem.actionable) continue;
        const response = await apiFetch(
          `/projects/${projectId}/m5/claims/${claimReview.review_id}/suggestions/${item.id}/${action}`,
          { method: "POST" },
        ) as { review?: ClaimReview; chapter_name?: ChapterName; chapter?: { prose?: string; document_fingerprint?: string } };
        if (response.review) {
          latestReview = response.review;
          setClaimReview(response.review);
        }
        if (action === "accept" && response.chapter_name && typeof response.chapter?.prose === "string") {
          onClaimAccepted({ revision: `${item.id}:${Date.now()}`, chapterName: response.chapter_name,
            prose: response.chapter.prose, documentFingerprint: response.chapter.document_fingerprint });
        }
      }
    } catch (error) {
      setClaimActionError(error instanceof Error ? error.message : "Không thể xử lý toàn bộ đề xuất.");
    } finally {
      setClaimBulkBusy(null);
    }
  }, [claimBulkBusy, claimReview, onClaimAccepted, projectId, thesisSave]);

  // beforeunload warning if dirty — prevents data loss if user navigates away
  // without re-exporting unsaved prose changes.
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (editsSinceExport > 0) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [editsSinceExport]);

  // Scrollspy: highlight the outline entry for whichever chapter is at the top
  // of the viewport as the user scrolls the one-page document. rootMargin's
  // -70% bottom inset means a section counts as "current" once its top passes
  // the upper third — so the highlight flips as a heading reaches the top,
  // not when the section is merely peeking in from the bottom.
  // Canonical keys only — same filter as `presentNames` below (which cannot be
  // reused here: it is computed after the early returns, and this hook must run
  // unconditionally). A non-canonical key has no rendered section to observe.
  const chapterKeys = chapters
    ? CHAPTER_ORDER.map(c => c.name).filter(n => chapters[n]).join(",")
    : "";
  useEffect(() => {
    const root = scrollRef.current;
    if (!root || !chapterKeys) return;
    const obs = new IntersectionObserver(
      entries => {
        const top = entries
          .filter(e => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        const name = top?.target.getAttribute("data-chapter");
        if (name) setActive(name as ChapterName);
      },
      { root, rootMargin: "0px 0px -70% 0px", threshold: 0 },
    );
    chapterKeys.split(",").forEach(n => {
      const el = document.getElementById(chapterAnchor(n));
      if (el) obs.observe(el);
    });
    return () => obs.disconnect();
  }, [chapterKeys]);

  if (!chapters) return <EditorSkeleton />;
  if (Object.keys(chapters).length === 0) return <EmptyState projectId={projectId} />;

  // Canonical chapters only, in canonical order. Rendering raw Object.keys
  // put a pane on screen for any key the API happened to return — including a
  // pre-branch project's retired `discussion` key, which is typeable but whose
  // every save PATCH 404s (_VALID_CHAPTER_NAMES no longer accepts it) and
  // parks an error the student cannot clear. The backfill now folds that prose
  // into `conclusion`; this makes an unrenderable key impossible regardless.
  const presentNames = CHAPTER_ORDER
    .map(c => c.name)
    .filter(name => chapters[name]) as ChapterName[];
  const tocChapters = Object.fromEntries(Object.entries(chapters).map(([name, chapter]) => [
    name,
    { ...chapter, prose: liveProse[name] ?? chapter.prose },
  ])) as ChapterDict;
  const contents = _headingContents(tocChapters);
  const reviewSuggestions = (claimReview?.suggestions ?? []).filter(
    item => item.status === "pending" && item.actionable,
  );
  const reviewPosition = Math.min(claimCursor, Math.max(reviewSuggestions.length - 1, 0));
  const currentReviewSuggestion = reviewSuggestions[reviewPosition];
  const goToReviewSuggestion = (next: number) => {
    const bounded = Math.max(0, Math.min(reviewSuggestions.length - 1, next));
    setClaimCursor(bounded);
    const item = reviewSuggestions[bounded];
    if (item) scrollToChapter(item.chapter);
  };

  return (
    // h-full (not min-h-screen) so this fills the bounded shell exactly; the
    // body row gets min-h-0 so it can shrink below its content height, which is
    // what lets the shared scroll container take over instead of the whole
    // column overflowing the clipped (overflow-hidden) shell.
    <div className="editor-workspace flex h-full flex-col bg-[#f3f3f1]">
      <ReExportBar
        lastExportAt={lastExportAt}
        editsSinceExport={editsSinceExport}
        onReExport={handleReExport}
        exporting={exporting}
        error={exportError}
        projectId={projectId}
        artifacts={artifacts}
        save={
          <SaveBar
            dirty={thesisSave.dirty}
            saving={thesisSave.saving}
            lastSavedAt={thesisSave.lastSavedAt}
            error={thesisSave.error}
            onSave={() => { void thesisSave.save(); }}
            onShowChanges={() => setChanges(thesisSave.changes())}
          />
        }
        onBackToChat={onBackToChat}
      />
      {changes && (
        <UnsavedDiff
          changes={changes}
          onClose={() => setChanges(null)}
          onSave={() => { void thesisSave.save(); }}
        />
      )}
      <div className="flex min-h-0 flex-1">
        {/* Outline click scrolls to the chapter; scrollspy keeps it in sync. */}
        <OutlineRail
          present={presentNames}
          active={active}
          onSelect={scrollToChapter}
          contents={contents}
          onSelectHeading={scrollToHeading}
        />

        {/* Center column: one shared toolbar pinned on top, every chapter
            stacked in a single scroll container below — the whole thesis reads
            as one continuous page. */}
        <main className="min-w-0 flex-1 flex flex-col min-h-0">
          {activeEditor && !activeEditor.isDestroyed && (
            <EditorToolbar
              editor={activeEditor}
              fontFamily={font.family}
              fontSize={font.size}
              lineHeight={font.lineHeight ?? _DEFAULT_LAYOUT.lineHeight}
              paraGap={font.paraGap ?? _DEFAULT_LAYOUT.paraGap}
              onFontFamily={family => setFont(f => ({ ...f, family }))}
              onFontSize={size => setFont(f => ({ ...f, size }))}
              onSpacing={(lineHeight, paraGap) => setFont(f => ({ ...f, lineHeight, paraGap }))}
            />
          )}
          <div ref={scrollRef} className="editor-canvas flex-1 overflow-y-auto px-6 py-8 lg:px-10">
            <article className="editor-paper mx-auto min-h-full max-w-[900px] bg-white px-[clamp(2rem,7vw,6.25rem)] py-[clamp(2.5rem,6vw,5.5rem)] shadow-[0_1px_2px_rgba(24,31,50,0.08),0_18px_55px_rgba(24,31,50,0.08)] ring-1 ring-black/[0.04]">
            <DocumentToc
              title={projectMeta?.context_store?.m1_topic?.research_title || projectMeta?.name || "Luận văn"}
              items={contents}
              onSelect={scrollToHeading}
              onSelectChapter={scrollToChapter}
            />
            {presentNames.map((name, index) => {
              const chapter = chapters[name];
              if (!chapter) return null;
              return (
                // No chapter heading here. The prose carries its own ("1.1 Bối
                // cảnh…"), and this printed the raw storage key — INTRO,
                // LIT_REVIEW — which both leaked an internal name and drew the
                // seams of a document the student is meant to read straight
                // through. The outline rail still navigates by these anchors.
                <section key={name} id={chapterAnchor(name)} data-chapter={name} className="mt-16 border-t border-ink-100 pt-14 scroll-mt-8">
                  <ChapterEditor
                    projectId={projectId}
                    chapterName={name}
                    initialProse={chapter.prose}
                    media={chapter.media ?? []}
                    renderableTokens={chapter.renderable_tokens ?? []}
                    documentFingerprint={chapter.document_fingerprint}
                    claimServerUpdate={claimUpdates[name] ?? null}
                    onSeed={(prose, fingerprint) => thesisSave.seed(name, prose, fingerprint)}
                    onServerProse={(prose, fingerprint) => thesisSave.reconcileServer(name, prose, fingerprint)}
                    onServerBaseline={(prose, fingerprint) => thesisSave.updateServerBaseline(name, prose, fingerprint)}
                    pendingEdits={_toPendingEdits(chapter.pending_edits)}
                    onPendingMutate={onPendingMutate}
                    onProseChange={prose => trackProse(name, prose)}
                    fontFamily={font.family}
                    fontSize={font.size}
                    lineHeight={font.lineHeight ?? _DEFAULT_LAYOUT.lineHeight}
                    paraGap={font.paraGap ?? _DEFAULT_LAYOUT.paraGap}
                    onActiveEditor={setActiveEditor}
                    onCitationClick={setHighlightedSource}
                    claimSuggestions={claimReviewOpen ? reviewSuggestions.filter(item => item.chapter === name) : []}
                    onClaimDecision={decideClaimInline}
                  />
                </section>
              );
            })}
            </article>
          </div>
          {claimReviewOpen && currentReviewSuggestion && <div className="z-40 flex shrink-0 items-center justify-center border-t border-ink-200 bg-white/95 px-4 py-2.5 shadow-[0_-8px_30px_rgba(24,31,50,0.08)] backdrop-blur">
            <div className="flex w-full max-w-[900px] items-center gap-2 text-xs">
              <button type="button" onClick={() => setClaimReviewOpen(false)} className="mr-auto inline-flex h-9 items-center gap-1.5 rounded-lg px-3 font-semibold text-ink-700 hover:bg-ink-50"><X className="h-4 w-4" />Tiếp tục chỉnh sửa</button>
              <button type="button" disabled={Boolean(claimBulkBusy)} onClick={() => void decideClaimsBulk("reject")} className="h-9 rounded-lg px-3 font-semibold text-ink-700 hover:bg-ink-50 disabled:opacity-45">Bỏ qua tất cả</button>
              <button type="button" disabled={Boolean(claimBulkBusy)} onClick={() => void decideClaimsBulk("accept")} className="h-9 rounded-lg px-3 font-semibold text-ink-700 hover:bg-ink-50 disabled:opacity-45">{claimBulkBusy === "accept" ? "Đang áp dụng…" : "Chấp nhận tất cả"}</button>
              <span className="mx-1 h-6 w-px bg-ink-200" />
              <button type="button" aria-label="Đề xuất trước" disabled={reviewPosition === 0 || Boolean(claimBulkBusy)} onClick={() => goToReviewSuggestion(reviewPosition - 1)} className="rounded-lg p-2 text-ink-600 hover:bg-ink-50 disabled:opacity-30"><ChevronLeft className="h-4 w-4" /></button>
              <span className="min-w-[56px] text-center font-semibold tabular-nums text-ink-700">{reviewPosition + 1}/{reviewSuggestions.length}</span>
              <button type="button" aria-label="Đề xuất tiếp" disabled={reviewPosition >= reviewSuggestions.length - 1 || Boolean(claimBulkBusy)} onClick={() => goToReviewSuggestion(reviewPosition + 1)} className="rounded-lg p-2 text-ink-600 hover:bg-ink-50 disabled:opacity-30"><ChevronRight className="h-4 w-4" /></button>
              <span className="mx-1 h-6 w-px bg-ink-200" />
              <button type="button" disabled={Boolean(claimBulkBusy)} onClick={() => void decideClaimInline(currentReviewSuggestion, "reject")} className="inline-flex h-9 items-center gap-1.5 rounded-lg px-3 font-semibold text-ink-700 hover:bg-ink-50 disabled:opacity-45"><X className="h-4 w-4" />Bỏ qua</button>
              <button type="button" disabled={Boolean(claimBulkBusy)} onClick={() => void decideClaimInline(currentReviewSuggestion, "accept")} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-primary-600 px-4 font-semibold text-white hover:bg-primary-700 disabled:opacity-45">{claimBulkBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}Chấp nhận</button>
            </div>
          </div>}
          {claimActionError && <p role="alert" className="m-0 shrink-0 border-t border-red-100 bg-red-50 px-4 py-2 text-center text-xs text-red-700">{claimActionError}</p>}
        </main>

        <EditorSidePanel projectId={projectId} highlightedSource={highlightedSource} onSelectChapter={scrollToChapter}
          onFlush={thesisSave.save} onClaimAccepted={onClaimAccepted} onClaimReviewChange={setClaimReview} claimReview={claimReview}
          onOpenClaimReview={() => { setClaimReviewOpen(true); setClaimCursor(0); }} />
      </div>
    </div>
  );
}
