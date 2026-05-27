"use client";

import { useEditor, EditorContent } from "@tiptap/react";
// BubbleMenu moved to a dedicated sub-path in TipTap v3 (no longer exported from
// @tiptap/react root). Import from the menus sub-path per v3 migration guide.
import { BubbleMenu } from "@tiptap/react/menus";
import StarterKit from "@tiptap/starter-kit";
import { useEffect, useState, useCallback, useRef } from "react";

import { AiPending } from "./extensions/AiPending";
import { CitationMark } from "./extensions/CitationMark";
import { SelectionToolbar } from "./SelectionToolbar";
import { CitePopover } from "./CitePopover";
import { TranslateMenu } from "./TranslateMenu";
import { PendingEditRibbon, type PendingEdit } from "./PendingEditRibbon";
import { useChapterAutosave } from "./hooks/useChapterAutosave";


type Props = {
  projectId: string;
  chapterName: string;
  initialProse: string;
  pendingEdits: PendingEdit[];
  defaultTargetLang?: string;
  onPendingMutate: () => void;
  onDirty: (dirty: boolean) => void;
};


// Mounts one TipTap instance per chapter. Owns:
//   - autosave (PATCH on debounced edit)
//   - selection toolbar (paraphrase/translate/cite via BubbleMenu)
//   - pending-edit reconciliation (apply AiPending marks for each server edit,
//     remove marks no longer on the server, surface accept/reject handlers per ribbon)
//   - stale-state tracking (accept that 409'd flips that edit's ribbon to "Discard")
export function ChapterEditor({
  projectId, chapterName, initialProse, pendingEdits,
  defaultTargetLang, onPendingMutate, onDirty,
}: Props) {
  const [showCite, setShowCite] = useState(false);
  const [showTranslate, setShowTranslate] = useState(false);
  const [staleIds, setStaleIds] = useState<Set<string>>(new Set());
  const selectionRef = useRef<{ from: number; to: number } | null>(null);

  const autosave = useChapterAutosave({ projectId, chapterName });

  const editor = useEditor({
    extensions: [StarterKit, AiPending, CitationMark],
    content: `<p>${initialProse.replace(/\n/g, "</p><p>")}</p>`,
    onUpdate({ editor }) {
      // Queue a debounced PATCH each time the document changes.
      const text = editor.getText();
      autosave.queue(text);
      onDirty(true);
    },
    onSelectionUpdate({ editor }) {
      // Track selection so toolbar action handlers can read from/to without
      // closing over a stale editor state reference.
      const { from, to } = editor.state.selection;
      selectionRef.current = from === to ? null : { from, to };
    },
    // In JSDOM (tests) and browser contexts, render immediately. The caller
    // is expected to mount ChapterEditor only after hydration (client-side),
    // so SSR mismatches are not a concern here.
    immediatelyRender: typeof window !== "undefined",
  });

  // Apply AiPending marks for every pending edit not already marked.
  // Remove marks whose pending_id is no longer in the list.
  // Decision: we reconcile on each pendingEdits change rather than keeping a
  // local "applied" set, so a re-fetch always reflects server truth.
  useEffect(() => {
    if (!editor) return;
    const currentIds = new Set(pendingEdits.map(e => e.id));

    // Remove marks for edits that are no longer on the server.
    editor.state.doc.descendants((node, pos) => {
      node.marks.forEach(m => {
        if (m.type.name === "aiPending" && !currentIds.has(m.attrs.pendingId)) {
          editor.chain()
            .setTextSelection({ from: pos, to: pos + node.nodeSize })
            .unsetMark("aiPending")
            .run();
        }
      });
    });

    // Add marks for edits that aren't yet reflected in the document.
    pendingEdits.forEach(edit => {
      const hasMark = (() => {
        let found = false;
        editor.state.doc.descendants(node => {
          if (found) return false;
          node.marks.forEach(m => {
            if (m.type.name === "aiPending" && m.attrs.pendingId === edit.id) found = true;
          });
          return !found;
        });
        return found;
      })();
      if (hasMark) return;

      // PM positions are 1-based at the doc top (position 0 is before the root
      // node's open tag). The +1 maps byte offsets returned by the server into
      // valid ProseMirror positions. Offset correctness is verified by e2e (Task 38).
      const from = edit.from_offset + 1;
      const to = edit.to_offset + 1;
      if (from <= to && to <= editor.state.doc.content.size) {
        const markType = editor.schema.marks.aiPending;
        const tr = editor.state.tr;
        editor.view.dispatch(
          tr.addMark(from, to === from ? from + 1 : to, markType.create({
            pendingId: edit.id,
            source: edit.source,
            oldText: edit.oldText,
            newText: edit.newText,
          }))
        );
      }
    });
  }, [editor, pendingEdits]);

  // Action handlers — each one captures the current selection then POSTs the relevant endpoint.
  const _withSelection = useCallback(async (kind: "paraphrase" | "translate" | "cite", body: any) => {
    const sel = selectionRef.current;
    if (!sel && kind !== "cite") return;
    const url = `/api/v1/projects/${projectId}/m5/chapters/${chapterName}/${kind}`;
    const payload = kind === "cite"
      ? { at_offset: editor?.state.selection.from ? editor.state.selection.from - 1 : 0, ...body }
      : { from_offset: sel!.from - 1, to_offset: sel!.to - 1, ...body };
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (r.ok) onPendingMutate();
  }, [projectId, chapterName, editor, onPendingMutate]);

  // Accept: POST to server. If 409 (stale conflict), mark the ribbon as stale
  // instead of removing it — user must "Discard" rather than "Accept".
  const handleAccept = useCallback(async (editId: string) => {
    const r = await fetch(
      `/api/v1/projects/${projectId}/m5/chapters/${chapterName}/pending/${editId}/accept`,
      { method: "POST" }
    );
    if (r.status === 409) {
      setStaleIds(prev => new Set(prev).add(editId));
      return;
    }
    if (r.ok) onPendingMutate();
  }, [projectId, chapterName, onPendingMutate]);

  // Reject: POST to server, then clear any stale flag for this edit.
  const handleReject = useCallback(async (editId: string) => {
    const r = await fetch(
      `/api/v1/projects/${projectId}/m5/chapters/${chapterName}/pending/${editId}/reject`,
      { method: "POST" }
    );
    if (r.ok) {
      setStaleIds(prev => {
        const next = new Set(prev);
        next.delete(editId);
        return next;
      });
      onPendingMutate();
    }
  }, [projectId, chapterName, onPendingMutate]);

  // Flip dirty flag back to false once autosave confirms a successful write.
  useEffect(() => {
    if (autosave.lastSavedAt) onDirty(false);
  }, [autosave.lastSavedAt, onDirty]);

  if (!editor) return <div>Loading editor…</div>;

  return (
    <div className="flex-1 px-8 py-6 overflow-y-auto">
      {/* BubbleMenu appears on text selection; children switch between toolbar
          modes (default → translate picker → citation search). */}
      <BubbleMenu editor={editor}>
        {!showCite && !showTranslate && (
          <SelectionToolbar
            onParaphrase={() => _withSelection("paraphrase", {})}
            onTranslate={() => setShowTranslate(true)}
            onCite={() => setShowCite(true)}
          />
        )}
        {showTranslate && (
          <TranslateMenu
            defaultLang={defaultTargetLang || "vi"}
            onConfirm={(targetLang) => {
              void _withSelection("translate", { target_lang: targetLang });
              setShowTranslate(false);
            }}
            onClose={() => setShowTranslate(false)}
          />
        )}
        {showCite && (
          <CitePopover
            projectId={projectId}
            onSelect={(refId) => {
              void _withSelection("cite", { reference_id: refId });
              setShowCite(false);
            }}
            onClose={() => setShowCite(false)}
          />
        )}
      </BubbleMenu>

      <EditorContent editor={editor} className="prose max-w-none" />

      {pendingEdits.length > 0 && (
        <div className="mt-6 border-t border-gray-200 pt-4 space-y-2">
          <div className="text-xs uppercase tracking-wider text-gray-400">
            Pending edits ({pendingEdits.length})
          </div>
          {pendingEdits.map(edit => (
            <div key={edit.id} className="bg-gray-50 rounded-md p-2 text-xs">
              <div className="text-gray-500 mb-1">
                <span className="line-through">{edit.oldText.slice(0, 80) || "(insertion)"}</span>
                {" → "}
                <span className="text-gray-900">{edit.newText.slice(0, 80)}</span>
              </div>
              <PendingEditRibbon
                edit={edit}
                onAccept={handleAccept}
                onReject={handleReject}
                stale={staleIds.has(edit.id)}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
