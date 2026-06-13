"use client";

import { useState, useEffect, useCallback } from "react";
import useSWR from "swr";

import { apiFetch } from "@/app/lib/api";
import { tokenStore } from "@/app/lib/tokenStore";

import { OutlineRail, type ChapterName } from "./OutlineRail";
import { ChapterEditor } from "./ChapterEditor";
import { SourcesRail } from "./SourcesRail";
import { ReExportBar } from "./ReExportBar";
import { EmptyState } from "./EmptyState";


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
    source: "paraphrase" | "translate" | "cite" | "chat_rewrite";
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
export function ThesisEditor({ projectId }: { projectId: string }) {
  const url = `/api/v1/projects/${projectId}/m5/chapters`;
  const { data: chapters, mutate } = useSWR<ChapterDict>(url, fetcher);
  const [active, setActive] = useState<ChapterName>("intro");
  const [lastExportAt, setLastExportAt] = useState<Date | null>(null);
  const [editsSinceExport, setEditsSinceExport] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<Error | null>(null);

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

  if (!chapters) return <div className="flex items-center justify-center min-h-screen text-gray-500">Loading…</div>;
  if (Object.keys(chapters).length === 0) return <EmptyState projectId={projectId} />;

  const presentNames = Object.keys(chapters) as ChapterName[];
  const activeChapter = chapters[active];

  return (
    <div className="flex flex-col min-h-screen">
      <ReExportBar
        lastExportAt={lastExportAt}
        editsSinceExport={editsSinceExport}
        onReExport={handleReExport}
        exporting={exporting}
        error={exportError}
      />
      <div className="flex flex-1">
        <OutlineRail present={presentNames} active={active} onSelect={setActive} />
        {activeChapter ? (
          <ChapterEditor
            key={active}
            projectId={projectId}
            chapterName={active}
            initialProse={activeChapter.prose}
            pendingEdits={_toPendingEdits(activeChapter.pending_edits)}
            onPendingMutate={onPendingMutate}
            onDirty={handleDirty}
          />
        ) : (
          <div className="flex-1 flex items-center justify-center text-gray-400">
            Select a chapter to edit.
          </div>
        )}
        <SourcesRail projectId={projectId} />
      </div>
    </div>
  );
}
