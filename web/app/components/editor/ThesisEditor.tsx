"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { type Editor } from "@tiptap/react";
import useSWR from "swr";

import { apiFetch } from "@/app/lib/api";
import { tokenStore } from "@/app/lib/tokenStore";

import { OutlineRail, CHAPTER_ORDER, type ChapterName } from "./OutlineRail";
import { ChapterEditor } from "./ChapterEditor";
import { EditorToolbar, FONT_FAMILIES } from "./EditorToolbar";
import { SourcesRail } from "./SourcesRail";
import { ReExportBar } from "./ReExportBar";
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
  pending_edits: Array<{
    id: string;
    source: "paraphrase" | "translate" | "cite" | "chat_rewrite" | "proofread" | "improve" | "humanize" | "expand" | "shorten";
    old_text: string;
    new_text: string;
    from_offset: number;
    to_offset: number;
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
  }));
}


// Top-level editor surface. Owns chapter selection state, edits-since-export
// counter, and orchestrates re-export. Per-chapter logic (autosave, AiPending,
// selection toolbar) lives inside ChapterEditor.
// Stable anchor id for a chapter section, so the outline can scroll to it.
const chapterAnchor = (name: string) => `ch-${name}`;


export function ThesisEditor({ projectId }: { projectId: string }) {
  const url = `/api/v1/projects/${projectId}/m5/chapters`;
  const { data: chapters, mutate } = useSWR<ChapterDict>(url, fetcher);
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
  const scrollRef = useRef<HTMLDivElement>(null);

  // Document-level font, persisted per project so the choice survives a reload
  // and applies across every stacked chapter. NOT a TipTap mark: chapters are
  // stored as clean markdown (html:false), so a font mark would be dropped on
  // the next autosave — a whole-document setting is lossless and how a thesis is
  // actually styled. Read lazily to avoid an SSR/client mismatch.
  const fontKey = `dothesis_editor_font_${projectId}`;
  const [font, setFont] = useState<{ family: string; size: number }>(() => {
    if (typeof window === "undefined") return { family: FONT_FAMILIES[0].value, size: 16 };
    try {
      const raw = window.localStorage.getItem(fontKey);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (typeof parsed?.family === "string" && Number.isFinite(parsed?.size)) return parsed;
      }
    } catch { /* corrupt value — fall through to the default */ }
    return { family: FONT_FAMILIES[0].value, size: 16 };
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

  const handleDirty = useCallback((dirty: boolean) => {
    if (dirty) setEditsSinceExport(n => n + 1);
  }, []);

  const handleReExport = useCallback(async () => {
    setExporting(true);
    setExportError(null);
    try {
      // apiFetch injects access_token + throws ApiError on non-2xx; replaces
      // the bare fetch that used to rely on the dothesis_session cookie.
      await apiFetch(`/projects/${projectId}/m5/export`, { method: "POST" });
      setLastExportAt(new Date());
      setEditsSinceExport(0);
    } catch (e: any) {
      setExportError(e);
    } finally {
      setExporting(false);
    }
  }, [projectId]);

  const onPendingMutate = useCallback(() => { void mutate(); }, [mutate]);

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
  // every autosave PATCH 404s (_VALID_CHAPTER_NAMES no longer accepts it) and
  // parks an error the student cannot clear. The backfill now folds that prose
  // into `conclusion`; this makes an unrenderable key impossible regardless.
  const presentNames = CHAPTER_ORDER
    .map(c => c.name)
    .filter(name => chapters[name]) as ChapterName[];

  return (
    // h-full (not min-h-screen) so this fills the bounded shell exactly; the
    // body row gets min-h-0 so it can shrink below its content height, which is
    // what lets the shared scroll container take over instead of the whole
    // column overflowing the clipped (overflow-hidden) shell.
    <div className="flex flex-col h-full">
      <ReExportBar
        lastExportAt={lastExportAt}
        editsSinceExport={editsSinceExport}
        onReExport={handleReExport}
        exporting={exporting}
        error={exportError}
      />
      <div className="flex flex-1 min-h-0">
        {/* Outline click scrolls to the chapter; scrollspy keeps it in sync. */}
        <OutlineRail present={presentNames} active={active} onSelect={scrollToChapter} />

        {/* Center column: one shared toolbar pinned on top, every chapter
            stacked in a single scroll container below — the whole thesis reads
            as one continuous page. */}
        <div className="flex-1 flex flex-col min-h-0">
          {activeEditor && (
            <EditorToolbar
              editor={activeEditor}
              fontFamily={font.family}
              fontSize={font.size}
              onFontFamily={family => setFont(f => ({ ...f, family }))}
              onFontSize={size => setFont(f => ({ ...f, size }))}
            />
          )}
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-8 py-6 space-y-12">
            {presentNames.map(name => {
              const chapter = chapters[name];
              if (!chapter) return null;
              return (
                <section key={name} id={chapterAnchor(name)} data-chapter={name} className="scroll-mt-4">
                  <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-400 mb-3">
                    {chapter.name}
                  </h2>
                  <ChapterEditor
                    projectId={projectId}
                    chapterName={name}
                    initialProse={chapter.prose}
                    pendingEdits={_toPendingEdits(chapter.pending_edits)}
                    onPendingMutate={onPendingMutate}
                    onDirty={handleDirty}
                    fontFamily={font.family}
                    fontSize={font.size}
                    onActiveEditor={setActiveEditor}
                    onCitationClick={setHighlightedSource}
                  />
                </section>
              );
            })}
          </div>
        </div>

        <SourcesRail projectId={projectId} highlightedId={highlightedSource} />
      </div>
    </div>
  );
}
