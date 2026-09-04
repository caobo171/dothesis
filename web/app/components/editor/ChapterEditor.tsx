"use client";

import { useEditor, EditorContent, type Editor } from "@tiptap/react";
// BubbleMenu moved to a dedicated sub-path in TipTap v3 (no longer exported from
// @tiptap/react root). Import from the menus sub-path per v3 migration guide.
import { BubbleMenu } from "@tiptap/react/menus";
import StarterKit from "@tiptap/starter-kit";
import { Table, TableRow, TableHeader, TableCell } from "@tiptap/extension-table";
import { Markdown } from "tiptap-markdown";
import { useEffect, useState, useCallback, useRef } from "react";

import { AiPending } from "./extensions/AiPending";
import { CitationMark } from "./extensions/CitationMark";
import { SlashCommand } from "./extensions/SlashCommand";
import { MermaidBlock } from "./extensions/MermaidBlock";
import { DtPlaceholder, preserveDtTokens } from "./extensions/DtPlaceholder";
import { CitationHighlight } from "./extensions/CitationHighlight";
import { SelectionToolbar } from "./SelectionToolbar";
import { CitePopover } from "./CitePopover";
import { TranslateMenu } from "./TranslateMenu";
import { PendingEditRibbon, type PendingEdit } from "./PendingEditRibbon";
import { useChapterAutosave } from "./hooks/useChapterAutosave";
import { buildOffsetMap, offsetToPos, posToOffset } from "./markdownOffset";
import { apiFetch, ApiError } from "@/app/lib/api";


type Props = {
  projectId: string;
  chapterName: string;
  initialProse: string;
  pendingEdits: PendingEdit[];
  defaultTargetLang?: string;
  onPendingMutate: () => void;
  onDirty: (dirty: boolean) => void;
  // Document font is owned by the parent (ThesisEditor) so one setting applies
  // across every stacked chapter and drives the single shared toolbar.
  fontFamily: string;
  fontSize: number;
  // Reports this chapter's editor to the parent when it gains focus, so the one
  // shared toolbar binds to whichever chapter the caret is in.
  onActiveEditor?: (editor: Editor) => void;
  // Clicking an inserted citation reports its reference id so the parent can
  // highlight the matching source in the rail.
  onCitationClick?: (referenceId: string) => void;
};


// Mounts one TipTap instance per chapter. Owns:
//   - autosave (PATCH on debounced edit)
//   - selection toolbar (paraphrase/translate/cite via BubbleMenu)
//   - pending-edit reconciliation (apply AiPending marks for each server edit,
//     remove marks no longer on the server, surface accept/reject handlers per ribbon)
//   - stale-state tracking (accept that 409'd flips that edit's ribbon to "Discard")
// The persistent formatting toolbar and the document font live in ThesisEditor
// now — with chapters stacked on one page, a per-chapter toolbar would repeat
// six times.
export function ChapterEditor({
  projectId, chapterName, initialProse, pendingEdits,
  defaultTargetLang, onPendingMutate, onDirty,
  fontFamily, fontSize, onActiveEditor, onCitationClick,
}: Props) {
  // Held in a ref so the useEditor config (built once) always calls the latest
  // handler without re-creating the editor.
  const citationClickRef = useRef(onCitationClick);
  citationClickRef.current = onCitationClick;
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
    // Table + its row/cell nodes: tiptap-markdown serializes them to GFM pipe
    // tables, which the Pandoc export renders — so tables survive autosave AND
    // land in the docx. resizable so columns can be dragged in the editor.
    // codeBlock:false disables StarterKit's plain code block so MermaidBlock (a
    // CodeBlock subclass, same "codeBlock" node name) takes its place — fenced
    // code still round-trips to markdown, but ```mermaid blocks now render a
    // live diagram preview.
    extensions: [
      StarterKit.configure({ codeBlock: false }),
      Markdown.configure({ html: false }), AiPending, CitationMark, SlashCommand,
      Table.configure({ resizable: true }), TableRow, TableHeader, TableCell,
      MermaidBlock, DtPlaceholder, CitationHighlight,
    ],
    // Apply prose styling + suppress the browser's default focus outline on the
    // contenteditable node itself. Putting the class here (not on EditorContent)
    // targets the inner `.ProseMirror` element — otherwise the wrapper styles
    // and the editable's blue focus ring fight, drawing a box around the column.
    editorProps: {
      // editor-prose (not `prose`): there's no @tailwindcss/typography plugin,
      // so `prose` was a dead class and headings rendered unstyled. editor-prose
      // carries the heading/list hierarchy and reads the font CSS vars set below.
      attributes: { class: "editor-prose max-w-none focus:outline-none" },
      // Clicking an inserted citation surfaces its source in the rail. Reads the
      // citation mark at the click position; non-citation clicks fall through.
      handleClick(view, pos) {
        const cm = view.state.doc.resolve(pos).marks().find(m => m.type.name === "citation");
        const refId = cm?.attrs.referenceId as string | undefined;
        if (refId) { citationClickRef.current?.(refId); return true; }
        return false;
      },
    },
    content: initialProse,
    onUpdate({ editor }) {
      // Persist markdown (not getText): getText would drop heading/emphasis
      // syntax now that they're structural nodes, corrupting the export. The
      // serializer round-trips the doc back to the same markdown dialect the
      // chapter was loaded from.
      // preserveDtTokens undoes the serializer's bracket-escaping so [[DT:kind]]
      // placement tokens stay intact for the export weave (see DtPlaceholder).
      const text = preserveDtTokens(editor.storage.markdown.getMarkdown());
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
  const _withSelection = useCallback(async (kind: "paraphrase" | "translate" | "cite" | "proofread" | "improve" | "humanize" | "expand" | "shorten", body: any) => {
    const sel = selectionRef.current;
    if (!sel && kind !== "cite") return;
    if (!editor) return;
    // apiFetch, NOT a raw fetch: the POST-only API reads the auth token from the
    // JSON body (no cookies), and a bare fetch sent none — so every inline
    // action 401'd with "missing access_token" and silently did nothing.
    const path = `/projects/${projectId}/m5/chapters/${chapterName}/${kind}`;
    // Convert PM positions to markdown char offsets so the server's
    // prose[from:to] splice targets exactly what the user selected.
    const map = buildOffsetMap(editor);
    const payload = kind === "cite"
      ? { at_offset: posToOffset(map, editor.state.selection.from), ...body }
      : { from_offset: posToOffset(map, sel!.from), to_offset: posToOffset(map, sel!.to), ...body };
    try {
      await apiFetch(path, { method: "POST", body: payload });
      onPendingMutate();
    } catch {
      // apiFetch redirects to /login on 401; other failures leave the selection
      // intact so the user can retry.
    }
  }, [projectId, chapterName, editor, onPendingMutate]);

  // Accept: POST to server. If 409 (stale conflict), mark the ribbon as stale
  // instead of removing it — user must "Discard" rather than "Accept".
  const handleAccept = useCallback(async (editId: string) => {
    try {
      await apiFetch(
        `/projects/${projectId}/m5/chapters/${chapterName}/pending/${editId}/accept`,
        { method: "POST" }
      );
      onPendingMutate();
    } catch (e) {
      // 409 = stale conflict: keep the ribbon but mark it, so the user discards
      // rather than accepts. Any other error is swallowed (apiFetch handles 401).
      if (e instanceof ApiError && e.status === 409) {
        setStaleIds(prev => new Set(prev).add(editId));
      }
    }
  }, [projectId, chapterName, onPendingMutate]);

  // Reject: POST to server, then clear any stale flag for this edit.
  const handleReject = useCallback(async (editId: string) => {
    try {
      await apiFetch(
        `/projects/${projectId}/m5/chapters/${chapterName}/pending/${editId}/reject`,
        { method: "POST" }
      );
      setStaleIds(prev => {
        const next = new Set(prev);
        next.delete(editId);
        return next;
      });
      onPendingMutate();
    } catch {
      // apiFetch handles 401; leave the ribbon so the user can retry.
    }
  }, [projectId, chapterName, onPendingMutate]);

  // Flip dirty flag back to false once autosave confirms a successful write.
  useEffect(() => {
    if (autosave.lastSavedAt) onDirty(false);
  }, [autosave.lastSavedAt, onDirty]);

  // Bind the shared toolbar to this chapter when it's ready and whenever it
  // gains focus, so formatting acts on the chapter the caret is actually in.
  useEffect(() => {
    if (!editor) return;
    onActiveEditor?.(editor);
    const handler = () => onActiveEditor?.(editor);
    editor.on("focus", handler);
    return () => { editor.off("focus", handler); };
  }, [editor, onActiveEditor]);

  // Brief per-chapter fallback while this TipTap instance boots. A few muted
  // lines (not raw "Loading…" text) so a stacked chapter doesn't flash a label.
  if (!editor) return (
    <div className="animate-pulse space-y-3 py-2" aria-hidden="true">
      <div className="h-3.5 w-11/12 rounded bg-ink-100" />
      <div className="h-3.5 w-4/5 rounded bg-ink-100" />
      <div className="h-3.5 w-full rounded bg-ink-100" />
    </div>
  );

  return (
    // Just the chapter body now — no toolbar, no own scroll. The parent stacks
    // these in one shared scroll container so the whole thesis reads as one page.
    <div>
      {/* BubbleMenu appears on text selection; children switch between toolbar
          modes (default → translate picker → citation search). */}
      <BubbleMenu editor={editor}>
        {!showCite && !showTranslate && (
          <SelectionToolbar
            onParaphrase={() => _withSelection("paraphrase", {})}
            onTranslate={() => setShowTranslate(true)}
            onCite={() => setShowCite(true)}
            onProofread={() => _withSelection("proofread", {})}
            onImprove={() => _withSelection("improve", {})}
            onHumanize={() => _withSelection("humanize", {})}
            onExpand={() => _withSelection("expand", {})}
            onShorten={() => _withSelection("shorten", {})}
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

      {/* Drive the document font through CSS variables the .editor-prose rules
          consume — this lets headings inherit the family while keeping their own
          sizes, and never touches the stored markdown. */}
      <div
        style={{
          ["--editor-font-family" as string]: fontFamily,
          ["--editor-font-size" as string]: `${fontSize}px`,
        }}
      >
        <EditorContent editor={editor} />
      </div>

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
