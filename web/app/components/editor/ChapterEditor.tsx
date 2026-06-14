"use client";

import { useEditor, EditorContent } from "@tiptap/react";
// BubbleMenu moved to a dedicated sub-path in TipTap v3 (no longer exported from
// @tiptap/react root). Import from the menus sub-path per v3 migration guide.
import { BubbleMenu } from "@tiptap/react/menus";
import StarterKit from "@tiptap/starter-kit";
import { Markdown } from "tiptap-markdown";
import { useEffect, useState, useCallback, useRef } from "react";

import { AiPending } from "./extensions/AiPending";
import { CitationMark } from "./extensions/CitationMark";
import { SlashCommand } from "./extensions/SlashCommand";
import { SelectionToolbar } from "./SelectionToolbar";
import { CitePopover } from "./CitePopover";
import { TranslateMenu } from "./TranslateMenu";
import { PendingEditRibbon, type PendingEdit } from "./PendingEditRibbon";
import { useChapterAutosave } from "./hooks/useChapterAutosave";
import { buildOffsetMap, offsetToPos, posToOffset } from "./markdownOffset";


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
    // Markdown extension makes the editor parse `initialProse` (stored markdown)
    // into real nodes — so `## 1.1` renders as an H2 instead of literal text —
    // and serializes back to markdown on save. html:false keeps raw HTML out of
    // the stored prose (and out of the exporter), so storage stays clean
    // markdown exactly like the exporter already expects.
    extensions: [StarterKit, Markdown.configure({ html: false }), AiPending, CitationMark, SlashCommand],
    // Apply prose styling + suppress the browser's default focus outline on the
    // contenteditable node itself. Putting the class here (not on EditorContent)
    // targets the inner `.ProseMirror` element — otherwise the wrapper styles
    // and the editable's blue focus ring fight, drawing a box around the column.
    editorProps: {
      attributes: { class: "prose max-w-none focus:outline-none" },
    },
    content: initialProse,
    onUpdate({ editor }) {
      // Persist markdown (not getText): getText would drop heading/emphasis
      // syntax now that they're structural nodes, corrupting the export. The
      // serializer round-trips the doc back to the same markdown dialect the
      // chapter was loaded from.
      const text = editor.storage.markdown.getMarkdown();
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

    // Build the offset map once, after the removal pass has settled, so every
    // edit resolves against the same serialized markdown / doc positions.
    const offsetMap = buildOffsetMap(editor);
    const docSize = editor.state.doc.content.size;

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

      // Server offsets are char positions in the markdown prose; map them to PM
      // positions through the serialized-markdown alignment (see markdownOffset).
      const from = offsetToPos(offsetMap, docSize, edit.from_offset);
      const to = offsetToPos(offsetMap, docSize, edit.to_offset);
      if (from <= to && to <= docSize) {
        const markType = editor.schema.marks.aiPending;
        const tr = editor.state.tr;
        editor.view.dispatch(
          tr.addMark(from, to === from ? Math.min(from + 1, docSize) : to, markType.create({
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
    if (!editor) return;
    const url = `/api/v1/projects/${projectId}/m5/chapters/${chapterName}/${kind}`;
    // Convert PM positions to markdown char offsets so the server's
    // prose[from:to] splice targets exactly what the user selected.
    const map = buildOffsetMap(editor);
    const payload = kind === "cite"
      ? { at_offset: posToOffset(map, editor.state.selection.from), ...body }
      : { from_offset: posToOffset(map, sel!.from), to_offset: posToOffset(map, sel!.to), ...body };
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

      <EditorContent editor={editor} />

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
