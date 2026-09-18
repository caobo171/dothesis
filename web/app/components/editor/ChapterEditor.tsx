"use client";

import { useEditor, EditorContent, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Table, TableRow, TableHeader, TableCell } from "@tiptap/extension-table";
import { Markdown } from "tiptap-markdown";
import { useEffect, useState, useCallback, useRef } from "react";
import { createPortal } from "react-dom";
import { BookOpen, Check, ExternalLink, ShieldCheck, X } from "lucide-react";

import { AiPending } from "./extensions/AiPending";
import { AiProcessing } from "./extensions/AiProcessing";
import { CitationMark } from "./extensions/CitationMark";
import { SlashCommand } from "./extensions/SlashCommand";
import { MermaidBlock } from "./extensions/MermaidBlock";
import { DtPlaceholder, preserveDtTokens } from "./extensions/DtPlaceholder";
import { CitationHighlight } from "./extensions/CitationHighlight";
import { FigureBlock } from "./extensions/FigureBlock";
import { RenderedArtifactBlock } from "./extensions/RenderedArtifactBlock";
import { ClaimReviewMark } from "./extensions/ClaimReviewMark";
import { SelectionToolbar, type RewriteKind } from "./SelectionToolbar";
import { CitePopover } from "./CitePopover";
import { TranslateMenu } from "./TranslateMenu";
import { PendingEditRibbon, type PendingEdit } from "./PendingEditRibbon";
import { buildOffsetMap, offsetToPos, posToOffset, previewOffsetToStored } from "./markdownOffset";
import { apiFetch, apiPostStream, ApiError } from "@/app/lib/api";
import type { ClaimSuggestion } from "./ClaimConfidencePanel";


type Props = {
  projectId: string;
  chapterName: string;
  initialProse: string;
  /** Reversible artifact URLs supplied by the authenticated chapter response.
   * Browser-only previews are never persisted back into chapter prose. */
  media?: Array<{ source: string; preview_url: string }>;
  /** DT blocks the exporter can materialise from verified project state. */
  renderableTokens?: string[];
  pendingEdits: PendingEdit[];
  defaultTargetLang?: string;
  onPendingMutate: () => void;
  /** The chapter as the server has it, reported once on mount so the document
   *  can diff against it. Not `initialProse` directly: TipTap re-serialises the
   *  markdown, and the round-tripped form is what an edit will be compared to. */
  onSeed?: (prose: string, fingerprint?: string) => void;
  /** Clears the parent save queue after the mounted document safely adopts a
   * server response from an inline action or proposal acceptance. */
  onServerProse?: (prose: string, fingerprint?: string) => void;
  /** Updates the parent's saved baseline but intentionally keeps newer typing. */
  onServerBaseline?: (prose: string, fingerprint?: string) => void;
  documentFingerprint?: string;
  /** A claim-confidence acceptance committed by the side panel. The editor
   * adopts it only when no newer local typing exists. */
  claimServerUpdate?: { revision: string; prose: string; documentFingerprint?: string } | null;
  /** This chapter's markdown, on every edit. Saving is owned by ThesisEditor:
   *  the student reads one continuous document, so there is one Save for it,
   *  not one per chapter. */
  onProseChange: (prose: string) => void;
  // Document font is owned by the parent (ThesisEditor) so one setting applies
  // across every stacked chapter and drives the single shared toolbar.
  fontFamily: string;
  fontSize: number;
  /** Line height and the gap between paragraphs. Display settings, not content:
   *  markdown cannot store a blank line, so spacing typed into the document
   *  serialises to nothing. */
  lineHeight: number;
  paraGap: number;
  // Reports this chapter's editor to the parent when it gains focus, so the one
  // shared toolbar binds to whichever chapter the caret is in.
  onActiveEditor?: (editor: Editor) => void;
  // Clicking an inserted citation reports its reference id so the parent can
  // highlight the matching source in the rail.
  onCitationClick?: (referenceId: string) => void;
  claimSuggestions?: ClaimSuggestion[];
  onClaimDecision?: (suggestion: ClaimSuggestion, action: "accept" | "reject") => Promise<void>;
};

export async function syncChapterForInlineAction({ projectId, chapterName, prose, fingerprint }: {
  projectId: string; chapterName: string; prose: string; fingerprint?: string;
}) {
  try {
    return await apiFetch(`/projects/${projectId}/m5/chapters/${chapterName}`, {
      method: "PATCH", body: { prose, ...(fingerprint ? { expected_document_fingerprint: fingerprint } : {}) },
    }) as { prose?: string; document_fingerprint?: string };
  } catch (error) {
    const detail = error instanceof ApiError ? error.body?.error : undefined;
    if (!(error instanceof ApiError) || error.status !== 409 || detail?.code !== "stale_document") throw error;
    const chapters = await apiFetch(`/projects/${projectId}/m5/chapters`, { method: "POST" }) as Record<string, { prose?: string; document_fingerprint?: string }>;
    const latest = chapters?.[chapterName];
    if (!latest || latest.prose !== prose || !latest.document_fingerprint) {
      throw new Error("Bản trên máy chủ đã có nội dung khác. Hãy tải lại chương rồi chọn lại đoạn cần xử lý.");
    }
    return latest;
  }
}

type PendingEditApi = {
  id: string;
  source: PendingEdit["source"];
  old_text: string;
  new_text: string;
  from_offset: number;
  to_offset: number;
  metadata?: PendingEdit["metadata"] & { explanation?: string; processing_ms?: number };
};

// The action endpoint already returns the complete proposal. Normalising it at
// the editor boundary lets review open immediately instead of waiting for the
// chapter query to revalidate and then making the student find it below prose.
export function pendingEditFromApi(edit: PendingEditApi): PendingEdit {
  return {
    id: edit.id,
    source: edit.source,
    oldText: edit.old_text,
    newText: edit.new_text,
    from_offset: edit.from_offset,
    to_offset: edit.to_offset,
    explanation: edit.metadata?.explanation,
    processingMs: edit.metadata?.processing_ms,
    metadata: edit.metadata,
  };
}


// Mounts one TipTap instance per chapter. Owns:
//   - reporting edits upward (the document's single Save lives in the parent)
//   - selection toolbar (paraphrase/translate/cite via BubbleMenu)
//   - pending-edit reconciliation (apply AiPending marks for each server edit,
//     remove marks no longer on the server, surface accept/reject handlers per ribbon)
//   - stale-state tracking (accept that 409'd flips that edit's ribbon to "Discard")
// The persistent formatting toolbar and the document font live in ThesisEditor
// now — with chapters stacked on one page, a per-chapter toolbar would repeat
// six times.
export function ChapterEditor({
  projectId, chapterName, initialProse, media = [], renderableTokens = [], pendingEdits,
  defaultTargetLang, onPendingMutate, onProseChange, onSeed, onServerProse, onServerBaseline, documentFingerprint, claimServerUpdate,
  fontFamily, fontSize, lineHeight, paraGap, onActiveEditor, onCitationClick,
  claimSuggestions = [], onClaimDecision,
}: Props) {
  // Held in a ref so the useEditor config (built once) always calls the latest
  // handler without re-creating the editor.
  const citationClickRef = useRef(onCitationClick);
  citationClickRef.current = onCitationClick;
  const claimSuggestionsRef = useRef(claimSuggestions);
  claimSuggestionsRef.current = claimSuggestions;
  const mediaRef = useRef(media);
  mediaRef.current = media;
  // TipTap calls `onUpdate` for document transactions, including mark-only
  // reconciliation used by citation highlights and AI pending edits. Those
  // transactions do not change the stored Markdown, but previously each one
  // incremented "edits since export" and could make the number climb forever.
  // Keep the last canonical payload at the editor boundary and only report a
  // real prose change upstream.
  const lastEmittedProseRef = useRef(initialProse);
  // Do not apply a response over text written while it was in flight. The
  // fingerprint still makes any later Save fail closed instead of clobbering it.
  const serverProseRef = useRef(initialProse);
  const appliedClaimRevisionRef = useRef<string | null>(null);
  const fingerprintRef = useRef<string | undefined>(documentFingerprint);
  const actionInFlight = useRef(false);
  const [busyEditIds, setBusyEditIds] = useState<Set<string>>(new Set());
  const [showCite, setShowCite] = useState(false);
  const [showTranslate, setShowTranslate] = useState(false);
  const [selectionAnchor, setSelectionAnchor] = useState<{ left: number; top: number } | null>(null);
  const [staleIds, setStaleIds] = useState<Set<string>>(new Set());
  const [activePendingEdit, setActivePendingEdit] = useState<PendingEdit | null>(null);
  const [activeReviewExpanded, setActiveReviewExpanded] = useState(false);
  const [inlineAction, setInlineAction] = useState<
    { state: "loading" | "success" | "error"; message: string; action?: "reload_chapter" } | null
  >(null);
  const [streamingDraft, setStreamingDraft] = useState("");
  const [activeClaim, setActiveClaim] = useState<{ id: string; left: number; top: number } | null>(null);
  const [busyClaim, setBusyClaim] = useState<string | null>(null);
  const selectionRef = useRef<{ from: number; to: number; text: string } | null>(null);

  const claimSourceUrl = (suggestion: ClaimSuggestion) => {
    const direct = suggestion.source?.url;
    if (direct && /^https?:\/\//i.test(direct)) return direct;
    const doi = suggestion.source?.doi?.replace(/^https?:\/\/doi\.org\//i, "");
    return doi ? `https://doi.org/${doi}` : undefined;
  };


  const editor = useEditor({
    // Markdown extension makes the editor parse `initialProse` (stored markdown)
    // into real nodes — so `## 1.1` renders as an H2 instead of literal text —
    // and serializes back to markdown on save. html:false keeps raw HTML out of
    // the stored prose (and out of the exporter), so storage stays clean
    // markdown exactly like the exporter already expects.
    // Table + its row/cell nodes: tiptap-markdown serializes them to GFM pipe
    // tables, which the Pandoc export renders — so tables survive a save AND
    // land in the docx. resizable so columns can be dragged in the editor.
    // codeBlock:false disables StarterKit's plain code block so MermaidBlock (a
    // CodeBlock subclass, same "codeBlock" node name) takes its place — fenced
    // code still round-trips to markdown, but ```mermaid blocks now render a
    // live diagram preview.
    extensions: [
      StarterKit.configure({ codeBlock: false }),
      Markdown.configure({ html: false }), AiPending, AiProcessing, CitationMark, SlashCommand,
      FigureBlock.configure({ inline: false, allowBase64: true }),
      Table.configure({ resizable: true }), TableRow, TableHeader, TableCell,
      MermaidBlock, DtPlaceholder.configure({ availableKinds: renderableTokens }),
      RenderedArtifactBlock, CitationHighlight, ClaimReviewMark,
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
        const claim = view.state.doc.resolve(pos).marks().find(mark => mark.type.name === "claimReview");
        const suggestionId = claim?.attrs.suggestionId as string | undefined;
        if (suggestionId && claimSuggestionsRef.current.some(item => item.id === suggestionId)) {
          const coords = view.coordsAtPos(pos);
          setActiveClaim({ id: suggestionId, left: Math.min(window.innerWidth - 330, Math.max(330, coords.left)), top: Math.max(16, Math.min(window.innerHeight - 580, coords.bottom + 10)) });
          return true;
        }
        const cm = view.state.doc.resolve(pos).marks().find(m => m.type.name === "citation");
        const refId = cm?.attrs.referenceId as string | undefined;
        if (refId) { citationClickRef.current?.(refId); return true; }
        return false;
      },
      handleKeyDown(view, event) {
        if (event.key !== "Enter" && event.key !== " ") return false;
        const pos = view.state.selection.head;
        const claim = view.state.doc.resolve(pos).marks().find(mark => mark.type.name === "claimReview");
        const suggestionId = claim?.attrs.suggestionId as string | undefined;
        if (!suggestionId || !claimSuggestionsRef.current.some(item => item.id === suggestionId)) return false;
        const coords = view.coordsAtPos(pos);
        setActiveClaim({ id: suggestionId, left: Math.min(window.innerWidth - 330, Math.max(330, coords.left)), top: Math.max(16, Math.min(window.innerHeight - 580, coords.bottom + 10)) });
        event.preventDefault();
        return true;
      },
    },
    content: media.reduce(
      (prose, item) => prose.split(`](${item.source})`).join(`](${item.preview_url})`),
      initialProse,
    ),
    onUpdate({ editor }) {
      // Persist markdown (not getText): getText would drop heading/emphasis
      // syntax now that they're structural nodes, corrupting the export. The
      // serializer round-trips the doc back to the same markdown dialect the
      // chapter was loaded from.
      // preserveDtTokens undoes the serializer's bracket-escaping so [[DT:kind]]
      // placement tokens stay intact for the export weave (see DtPlaceholder).
      const displayed = preserveDtTokens(editor.storage.markdown.getMarkdown());
      const text = mediaRef.current.reduce(
        (prose, item) => prose.split(`](${item.preview_url})`).join(`](${item.source})`),
        displayed,
      );
      if (text === lastEmittedProseRef.current) return;
      lastEmittedProseRef.current = text;
      onProseChange(text);
    },
    onSelectionUpdate({ editor }) {
      // Track selection so toolbar action handlers can read from/to without
      // closing over a stale editor state reference. Keep the last non-empty
      // range when a portal textarea takes focus: TipTap may collapse its live
      // selection at that point, but the composer still belongs to the range
      // that opened it.
      const { from, to } = editor.state.selection;
      if (from === to) {
        setSelectionAnchor(null);
      } else {
        selectionRef.current = {
          from,
          to,
          text: editor.state.doc.textBetween(from, to, "\n\n", ""),
        };
        const start = editor.view.coordsAtPos(from);
        const end = editor.view.coordsAtPos(to);
        setSelectionAnchor({
          left: Math.max(180, Math.min(window.innerWidth - 180, (start.left + end.right) / 2)),
          top: Math.min(window.innerHeight - 72, Math.max(start.bottom, end.bottom) + 10),
        });
      }
    },
    // In JSDOM (tests) and browser contexts, render immediately. The caller
    // is expected to mount ChapterEditor only after hydration (client-side),
    // so SSR mismatches are not a concern here.
    immediatelyRender: typeof window !== "undefined",
  });

  // Report the chapter as the SERVER has it, once the editor has parsed it.
  // Not `initialProse` directly: TipTap re-serialises the markdown on the way
  // back out, so every future edit is compared against the round-tripped form.
  // Diffing against the raw stored string instead would show the serializer's
  // own normalisation as the student's changes.
  const seeded = useRef(false);
  useEffect(() => {
    if (!editor || seeded.current || !onSeed) return;
    seeded.current = true;
    const displayed = preserveDtTokens(editor.storage.markdown.getMarkdown());
    const canonical = mediaRef.current.reduce(
      (prose, item) => prose.split(`](${item.preview_url})`).join(`](${item.source})`),
      displayed,
    );
    // Seed the dedupe guard with TipTap's round-tripped representation. This
    // prevents serializer normalisation on mount from looking like a student
    // edit while preserving the exact same baseline used by the save hook.
    lastEmittedProseRef.current = canonical;
    serverProseRef.current = canonical;
    onSeed(canonical, fingerprintRef.current);
  }, [editor, onSeed]);

  useEffect(() => {
    if (!editor || !claimServerUpdate || appliedClaimRevisionRef.current === claimServerUpdate.revision) return;
    appliedClaimRevisionRef.current = claimServerUpdate.revision;
    const current = mediaRef.current.reduce(
      (prose, item) => prose.split(`](${item.preview_url})`).join(`](${item.source})`),
      preserveDtTokens(editor.storage.markdown.getMarkdown()),
    );
    // A claim action always flushes before its request. If typing resumed while
    // it waited, keep that local work visible and let the normal fingerprint
    // conflict protect it rather than replacing the student's newer prose.
    if (current !== serverProseRef.current) {
      setInlineAction({ state: "error", message: "Đề xuất đã được chấp nhận trên máy chủ, nhưng chương này có nội dung mới cục bộ. Nội dung cục bộ được giữ nguyên; hãy tải lại hoặc đối chiếu trước khi lưu." });
      return;
    }
    const displayed = mediaRef.current.reduce(
      (prose, item) => prose.split(`](${item.source})`).join(`](${item.preview_url})`),
      claimServerUpdate.prose,
    );
    editor.commands.setContent(displayed, { emitUpdate: false });
    const canonical = mediaRef.current.reduce(
      (prose, item) => prose.split(`](${item.preview_url})`).join(`](${item.source})`),
      preserveDtTokens(editor.storage.markdown.getMarkdown()),
    );
    lastEmittedProseRef.current = canonical;
    serverProseRef.current = canonical;
    fingerprintRef.current = claimServerUpdate.documentFingerprint ?? fingerprintRef.current;
    onServerProse?.(canonical, fingerprintRef.current);
  }, [claimServerUpdate, editor, onServerProse]);

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

  // Claim review anchors are server markdown offsets. Render them as transient
  // marks only while the exact captured text is still present; stale anchors
  // stay visible in the sidebar rather than highlighting the wrong sentence.
  useEffect(() => {
    if (!editor) return;
    const markType = editor.schema.marks.claimReview;
    let transaction = editor.state.tr.removeMark(0, editor.state.doc.content.size, markType);
    const offsetMap = buildOffsetMap(editor);
    const docSize = editor.state.doc.content.size;
    for (const suggestion of claimSuggestions) {
      if (suggestion.status !== "pending") continue;
      const { from_offset: fromOffset, to_offset: toOffset, old_text: oldText } = suggestion.anchor;
      if (!oldText || offsetMap.md.slice(fromOffset, toOffset) !== oldText) continue;
      const from = offsetToPos(offsetMap, docSize, fromOffset);
      const to = offsetToPos(offsetMap, docSize, toOffset);
      if (from < to && to <= docSize) {
        transaction = transaction.addMark(from, to, markType.create({ suggestionId: suggestion.id, actionable: suggestion.actionable }));
      }
    }
    if (transaction.docChanged || transaction.steps.length) editor.view.dispatch(transaction);
    if (activeClaim && !claimSuggestions.some(item => item.id === activeClaim.id && item.status === "pending")) setActiveClaim(null);
  }, [activeClaim, claimSuggestions, editor]);

  // Action handlers — each one captures the current selection then POSTs the relevant endpoint.
  const _withSelection = useCallback(async (kind: "paraphrase" | "translate" | "cite" | "proofread" | "improve" | "humanize" | "expand" | "shorten", body: any) => {
    if (actionInFlight.current) return;
    const sel = selectionRef.current;
    if (!sel && kind !== "cite") {
      setInlineAction({ state: "error", message: "Hãy chọn đoạn văn cần chỉnh sửa rồi thử lại." });
      return;
    }
    if (!editor) return;
    // apiFetch, NOT a raw fetch: the POST-only API reads the auth token from the
    // JSON body (no cookies), and a bare fetch sent none — so every inline
    // action 401'd with "missing access_token" and silently did nothing.
    const path = `/projects/${projectId}/m5/chapters/${chapterName}/${kind}`;
    // Convert PM positions to markdown char offsets so the server's
    // prose[from:to] splice targets exactly what the user selected.
    const map = buildOffsetMap(editor);
    const canonicalMarkdown = mediaRef.current.reduce(
      (prose, item) => prose.split(`](${item.preview_url})`).join(`](${item.source})`),
      preserveDtTokens(map.md),
    );
    const storedOffset = (pos: number) => previewOffsetToStored(
      map.md, posToOffset(map, pos), mediaRef.current,
    );
    // Academic citations belong at the end of the selected claim. When the
    // selection includes terminal punctuation, insert immediately before it so
    // the result is `claim (Author, Year).`, not `(Author, Year) claim` or
    // `claim. (Author, Year)`.
    let citePos = sel?.to ?? editor.state.selection.to;
    if (sel) {
      const selected = editor.state.doc.textBetween(sel.from, sel.to, "", "");
      const trailing = selected.match(/\s*([.!?。！？])\s*$/u);
      if (trailing) citePos = Math.max(sel.from, sel.to - trailing[0].length);
    }
    let fromOffset = sel ? storedOffset(sel.from) : storedOffset(citePos);
    let toOffset = sel ? storedOffset(sel.to) : fromOffset;
    if (kind !== "cite" && sel && (fromOffset === toOffset || !canonicalMarkdown.slice(fromOffset, toOffset).trim())) {
      // Some rich selections cross syntax runs that the markdown serializer
      // cannot align one-to-one. Recover only when the captured selection text
      // occurs exactly once; guessing between duplicate paragraphs would edit
      // the wrong passage.
      const first = canonicalMarkdown.indexOf(sel.text);
      const unique = first >= 0 && canonicalMarkdown.indexOf(sel.text, first + 1) === -1;
      if (!unique) {
        setInlineAction({ state: "error", message: "Không xác định được chính xác đoạn đã chọn. Hãy chọn lại một đoạn ngắn hơn rồi thử lại." });
        return;
      }
      fromOffset = first;
      toOffset = first + sel.text.length;
    }
    const payload = kind === "cite"
      ? { at_offset: storedOffset(citePos), ...body }
      : { from_offset: fromOffset, to_offset: toOffset, ...body };
    const processingMark = editor.schema.marks.aiProcessing;
    if (sel && processingMark) {
      editor.view.dispatch(editor.state.tr.addMark(sel.from, sel.to, processingMark.create()));
    }
    actionInFlight.current = true;
    setStreamingDraft("");
    setInlineAction({ state: "loading", message: "Đang xử lý đoạn đã chọn bằng AI…" });
    try {
      // The editor serializer normalises markdown and the student may also have
      // unsaved changes. Persist this exact canonical string first so the next
      // request's offsets are validated against the same bytes they came from.
      // Without this handshake, even ordinary heading/table normalisation can
      // make every inline action fail with offset_out_of_range.
      // The chapter may have been saved by the document-level Save or a claim
      // acceptance after this TipTap instance mounted. A stale revision is
      // refreshed only when the exact canonical prose still agrees.
      const patched = await syncChapterForInlineAction({ projectId, chapterName, prose: canonicalMarkdown, fingerprint: fingerprintRef.current });
      // A user may keep typing while the PATCH is in flight. Those new words
      // have no stable offset yet, so never create a proposal against them.
      if (lastEmittedProseRef.current !== canonicalMarkdown) {
        fingerprintRef.current = typeof patched?.document_fingerprint === "string"
          ? patched.document_fingerprint : fingerprintRef.current;
        // The direct PATCH did land. Keep its revision as the base for the
        // newer local draft so a later global Save can safely build on it.
        onServerBaseline?.(canonicalMarkdown, fingerprintRef.current);
        setInlineAction({ state: "error", message: "Nội dung đã thay đổi khi đang chuẩn bị đề xuất. Chọn lại đoạn văn rồi thử lại." });
        return;
      }
      serverProseRef.current = canonicalMarkdown;
      fingerprintRef.current = typeof patched?.document_fingerprint === "string"
        ? patched.document_fingerprint : fingerprintRef.current;
      onServerProse?.(canonicalMarkdown, fingerprintRef.current);
      if (fingerprintRef.current) payload.expected_document_fingerprint = fingerprintRef.current;
      const streamingKinds = new Set(["proofread", "improve", "humanize", "expand", "shorten"]);
      let createdApi: PendingEditApi;
      if (streamingKinds.has(kind)) {
        const terminal: any = await apiPostStream(`${path}/stream`, payload, (event: any) => {
          if (event.type === "token" && typeof event.text === "string") {
            setStreamingDraft(current => current + event.text);
          }
        });
        createdApi = terminal.edit as PendingEditApi;
      } else {
        createdApi = await apiFetch(path, { method: "POST", body: payload }) as PendingEditApi;
      }
      const created = pendingEditFromApi(createdApi);
      const pendingMark = editor.schema.marks.aiPending;
      if (sel && pendingMark) {
        editor.view.dispatch(editor.state.tr.addMark(sel.from, sel.to, pendingMark.create({
          pendingId: created.id,
          source: created.source,
          oldText: created.oldText,
          newText: created.newText,
        })));
      }
      setActivePendingEdit(created);
      setActiveReviewExpanded(false);
      setStreamingDraft("");
      setInlineAction(null);
      onPendingMutate();
    } catch (e) {
      // Keep the selection intact so the student can retry, but never turn a
      // server failure into a button that appears to do nothing.
      const message = e instanceof Error ? e.message : "Không thể xử lý đoạn đã chọn.";
      setInlineAction({
        state: "error",
        message,
        ...(message.startsWith("Bản trên máy chủ đã có nội dung khác") ? { action: "reload_chapter" as const } : {}),
      });
      setStreamingDraft("");
    } finally {
      const mark = editor.schema.marks.aiProcessing;
      if (mark) editor.view.dispatch(editor.state.tr.removeMark(0, editor.state.doc.content.size, mark));
      actionInFlight.current = false;
    }
  }, [projectId, chapterName, editor, onPendingMutate, onServerProse, onServerBaseline]);

  // Accept: POST to server. If 409 (stale conflict), mark the ribbon as stale
  // instead of removing it — user must "Discard" rather than "Accept".
  const handleAccept = useCallback(async (editId: string, mode: "replace" | "insert_after" = "replace") => {
    if (busyEditIds.has(editId)) return;
    setBusyEditIds(prev => new Set(prev).add(editId));
    try {
      const accepted: any = await apiFetch(
        `/projects/${projectId}/m5/chapters/${chapterName}/pending/${editId}/accept`,
        { method: "POST", body: {
          mode,
          ...(fingerprintRef.current ? { expected_document_fingerprint: fingerprintRef.current } : {}),
        } }
      );
      const nextProse = typeof accepted?.prose === "string" ? accepted.prose : null;
      const current = mediaRef.current.reduce(
        (prose, item) => prose.split(`](${item.preview_url})`).join(`](${item.source})`),
        preserveDtTokens(editor?.storage.markdown.getMarkdown() ?? ""),
      );
      if (nextProse !== null && current === serverProseRef.current && editor) {
        const displayed = mediaRef.current.reduce(
          (prose, item) => prose.split(`](${item.source})`).join(`](${item.preview_url})`),
          nextProse,
        );
        // Keep TipTap and its parent queue in sync without emitting a synthetic
        // edit that would later PATCH the pre-accept prose back over the server.
        editor.commands.setContent(displayed, { emitUpdate: false });
        const canonical = mediaRef.current.reduce(
          (prose, item) => prose.split(`](${item.preview_url})`).join(`](${item.source})`),
          preserveDtTokens(editor.storage.markdown.getMarkdown()),
        );
        lastEmittedProseRef.current = canonical;
        serverProseRef.current = canonical;
        fingerprintRef.current = typeof accepted?.document_fingerprint === "string"
          ? accepted.document_fingerprint : fingerprintRef.current;
        onServerProse?.(canonical, fingerprintRef.current);
      } else if (nextProse !== null) {
        setInlineAction({ state: "error", message: "Đề xuất đã được chấp nhận trên máy chủ, nhưng chương này có nội dung mới cục bộ. Nội dung cục bộ được giữ nguyên; hãy tải lại hoặc đối chiếu trước khi lưu." });
      }
      if (activePendingEdit?.id === editId) setActivePendingEdit(null);
      onPendingMutate();
    } catch (e) {
      // 409 = stale conflict: keep the ribbon but mark it, so the user discards
      // rather than accepts. Any other error is swallowed (apiFetch handles 401).
      if (e instanceof ApiError && e.status === 409) {
        setStaleIds(prev => new Set(prev).add(editId));
      } else {
        setInlineAction({ state: "error", message: e instanceof Error ? e.message : "Không thể chấp nhận đề xuất." });
      }
    } finally {
      setBusyEditIds(prev => { const next = new Set(prev); next.delete(editId); return next; });
    }
  }, [projectId, chapterName, editor, busyEditIds, onPendingMutate, onServerProse, activePendingEdit]);

  // Reject: POST to server, then clear any stale flag for this edit.
  const handleReject = useCallback(async (editId: string) => {
    if (busyEditIds.has(editId)) return;
    setBusyEditIds(prev => new Set(prev).add(editId));
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
      if (activePendingEdit?.id === editId) setActivePendingEdit(null);
      onPendingMutate();
    } catch (e) {
      // Keep the ribbon so the student can retry, and make the failure visible.
      setInlineAction({ state: "error", message: e instanceof Error ? e.message : "Không thể bỏ đề xuất." });
    } finally {
      setBusyEditIds(prev => { const next = new Set(prev); next.delete(editId); return next; });
    }
  }, [projectId, chapterName, busyEditIds, onPendingMutate, activePendingEdit]);

  const handleRetry = useCallback(async (edit: PendingEdit) => {
    if (edit.source === "chat_rewrite" || actionInFlight.current) return;
    const body: Record<string, unknown> = edit.source === "cite"
      ? { at_offset: edit.from_offset, reference_id: edit.metadata?.reference_id }
      : edit.source === "translate"
        ? { from_offset: edit.from_offset, to_offset: edit.to_offset, target_lang: edit.metadata?.target_lang || defaultTargetLang || "vi" }
        : {
            from_offset: edit.from_offset,
            to_offset: edit.to_offset,
            ...(edit.source === "paraphrase"
              ? { prompt: edit.metadata?.style || "" }
              : { prompt: edit.metadata?.prompt || "" }),
          };
    // Retries reuse offsets captured with the proposal. They must carry that
    // same snapshot revision (or the latest known revision for legacy edits),
    // so a moved chapter fails closed instead of regenerating at the wrong span.
    const retryFingerprint = edit.metadata?.document_fingerprint || fingerprintRef.current;
    if (retryFingerprint) body.expected_document_fingerprint = retryFingerprint;
    actionInFlight.current = true;
    setInlineAction({ state: "loading", message: "Đang lập kế hoạch và tạo lại đề xuất…" });
    try {
      // Create the replacement first. If generation fails, the existing
      // proposal remains reviewable instead of disappearing.
      const replacement = pendingEditFromApi(await apiFetch(
        `/projects/${projectId}/m5/chapters/${chapterName}/${edit.source}`,
        { method: "POST", body },
      ) as PendingEditApi);
      await apiFetch(`/projects/${projectId}/m5/chapters/${chapterName}/pending/${edit.id}/reject`, { method: "POST" });
      setActivePendingEdit(replacement);
      setActiveReviewExpanded(false);
      setInlineAction(null);
      onPendingMutate();
    } catch (e) {
      setInlineAction({ state: "error", message: e instanceof Error ? e.message : "Không thể tạo lại đề xuất." });
    } finally {
      actionInFlight.current = false;
    }
  }, [projectId, chapterName, defaultTargetLang, onPendingMutate]);

  const decideActiveClaim = useCallback(async (suggestion: ClaimSuggestion, action: "accept" | "reject") => {
    if (!onClaimDecision || busyClaim) return;
    setBusyClaim(suggestion.id);
    try {
      await onClaimDecision(suggestion, action);
      setActiveClaim(null);
    } catch (error) {
      setInlineAction({ state: "error", message: error instanceof Error ? error.message : "Không thể cập nhật đề xuất citation." });
    } finally {
      setBusyClaim(null);
    }
  }, [busyClaim, onClaimDecision]);

  const reloadChapterFromServer = useCallback(async () => {
    if (!editor) return;
    setInlineAction({ state: "loading", message: "Đang tải bản chương mới nhất…" });
    try {
      const chapters = await apiFetch(`/projects/${projectId}/m5/chapters`, { method: "POST" }) as Record<string, { prose?: string; document_fingerprint?: string }>;
      const latest = chapters?.[chapterName];
      if (!latest || typeof latest.prose !== "string") throw new Error("Không tải được chương mới nhất.");
      const displayed = mediaRef.current.reduce(
        (prose, item) => prose.split(`](${item.source})`).join(`](${item.preview_url})`),
        latest.prose,
      );
      editor.commands.setContent(displayed, { emitUpdate: false });
      const canonical = mediaRef.current.reduce(
        (prose, item) => prose.split(`](${item.preview_url})`).join(`](${item.source})`),
        preserveDtTokens(editor.storage.markdown.getMarkdown()),
      );
      lastEmittedProseRef.current = canonical;
      serverProseRef.current = canonical;
      fingerprintRef.current = latest.document_fingerprint ?? fingerprintRef.current;
      onServerProse?.(canonical, fingerprintRef.current);
      setInlineAction({ state: "success", message: "Đã tải bản chương mới nhất. Hãy chọn lại đoạn cần xử lý." });
    } catch (error) {
      setInlineAction({ state: "error", message: error instanceof Error ? error.message : "Không tải được chương mới nhất.", action: "reload_chapter" });
    }
  }, [chapterName, editor, onServerProse, projectId]);

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
      {activeClaim && (() => {
        const suggestion = claimSuggestions.find(item => item.id === activeClaim.id);
        if (!suggestion) return null;
        return (
          <aside role="dialog" aria-label="Đề xuất citation" className="fixed top-1/2 z-[85] flex max-h-[calc(100vh-2rem)] w-[min(620px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl border border-ink-200 bg-white shadow-[0_24px_70px_rgba(24,31,50,0.22)]"
            style={{ left: activeClaim.left }}>
            <div className="flex shrink-0 items-start justify-between gap-4 border-b border-ink-100 px-5 py-4">
              <div className="min-w-0"><p className="m-0 flex items-center gap-2 text-sm font-semibold text-ink-900"><span className="h-2.5 w-2.5 rounded-full bg-red-500" />{suggestion.actionable ? "Chưa có bằng chứng" : "Cần xem xét thêm"}</p>
                <p className="mb-0 mt-2 text-[13px] leading-5 text-ink-600">{suggestion.rationale_vi}</p></div>
              <button type="button" onClick={() => setActiveClaim(null)} aria-label="Đóng đề xuất" className="shrink-0 rounded-lg p-1.5 text-ink-400 hover:bg-ink-50 hover:text-ink-800"><X className="h-4 w-4" /></button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-4">
              {suggestion.source && <section aria-label="Nguồn tham khảo"><p className="m-0 text-xs font-semibold text-ink-800">Nguồn tham khảo</p>
                <div className="mt-3 rounded-xl border border-ink-200 bg-ink-50/70 p-4">
                  <div className="flex flex-wrap items-center gap-2 text-[10px] font-semibold uppercase tracking-[.04em] text-ink-500"><span>Bài báo</span>{suggestion.source.verified && <span className="inline-flex items-center gap-1 text-emerald-700"><ShieldCheck className="h-3.5 w-3.5" />Đã xác minh</span>}{suggestion.evidence?.kind === "full_text" && <span className="text-primary-700">Có toàn văn</span>}</div>
                  <p className="mb-0 mt-3 text-sm font-semibold leading-5 text-ink-900">{suggestion.source.title}</p>
                  <p className="mb-0 mt-1 text-xs text-ink-500">{suggestion.source.authors?.join(", ")}{suggestion.source.year ? ` · ${suggestion.source.year}` : ""}{suggestion.source.venue ? ` · ${suggestion.source.venue}` : ""}</p>
                  {suggestion.evidence?.text && <blockquote className="mb-0 mt-3 border-l-2 border-primary-300 pl-3 text-xs leading-5 text-ink-600">{suggestion.evidence.text}</blockquote>}
                  {claimSourceUrl(suggestion) && <a href={claimSourceUrl(suggestion)} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold text-primary-700 hover:underline"><BookOpen className="h-3.5 w-3.5" />Mở nguồn <ExternalLink className="h-3 w-3" /></a>}
                </div>
              </section>}
              {suggestion.proposed_text && <section className="mt-4"><p className="m-0 text-xs font-semibold text-ink-800">Nội dung sau khi chấp nhận</p><p className="mb-0 mt-2 rounded-xl bg-emerald-50 px-3 py-2.5 text-xs leading-5 text-emerald-900">{suggestion.proposed_text}</p></section>}
            </div>
            <div className="flex shrink-0 items-center justify-end gap-2 border-t border-ink-100 bg-white px-5 py-3.5">
              <button type="button" disabled={busyClaim === suggestion.id} onClick={() => void decideActiveClaim(suggestion, "reject")} className="inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-xs font-semibold text-ink-700 hover:bg-ink-50 disabled:opacity-45"><X className="h-4 w-4" />Bỏ qua</button>
              <button type="button" disabled={!suggestion.actionable || busyClaim === suggestion.id} onClick={() => void decideActiveClaim(suggestion, "accept")} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-primary-600 px-4 text-xs font-semibold text-white shadow-sm hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-45"><Check className="h-4 w-4" />{busyClaim === suggestion.id ? "Đang áp dụng…" : "Chấp nhận"}</button>
            </div>
          </aside>
        );
      })()}
      {/* Render outside TipTap's BubbleMenu lifecycle. BubbleMenu can be
          destroyed during pointer focus before nested actions finish their
          click. Editor coordinates retain contextual placement while the
          normal React tree reliably preserves Cite/Translate/AI state. */}
      {selectionAnchor && !showCite && !showTranslate && (
        <div
          className="fixed z-[75] -translate-x-1/2"
          style={{ left: selectionAnchor.left, top: selectionAnchor.top }}
        >
          <SelectionToolbar
            onRewrite={(kind: RewriteKind, prompt: string) => _withSelection(kind, { prompt })}
            onTranslate={() => setShowTranslate(true)}
            onCite={() => setShowCite(true)}
          />
        </div>
      )}

      {/* Pickers live outside BubbleMenu. TipTap owns and may hide/unmount the
          bubble as soon as a toolbar button receives focus; keeping the richer
          dialogs in React's normal tree makes Cite/Translate reliable while
          selectionRef preserves the exact range they act on. */}
      {showTranslate && (
        <div className="fixed left-1/2 top-24 z-[80] -translate-x-1/2">
          <TranslateMenu
            defaultLang={defaultTargetLang || "vi"}
            onConfirm={(targetLang) => {
              void _withSelection("translate", { target_lang: targetLang });
              setShowTranslate(false);
            }}
            onClose={() => setShowTranslate(false)}
          />
        </div>
      )}
      {showCite && (
        <div className="fixed left-1/2 top-24 z-[80] -translate-x-1/2">
          <CitePopover
            projectId={projectId}
            selectedText={selectionRef.current?.text || ""}
            onSelect={(refId) => {
              void _withSelection("cite", { reference_id: refId });
              setShowCite(false);
            }}
            onClose={() => setShowCite(false)}
          />
        </div>
      )}

      {/* Drive the document font through CSS variables the .editor-prose rules
          consume — this lets headings inherit the family while keeping their own
          sizes, and never touches the stored markdown. */}
      <div
        style={{
          ["--editor-font-family" as string]: fontFamily,
          ["--editor-font-size" as string]: `${fontSize}px`,
          ["--editor-line-height" as string]: String(lineHeight),
          ["--editor-para-gap" as string]: `${paraGap}px`,
        }}
      >
        <EditorContent editor={editor} />
      </div>

      {inlineAction && (
        <div
          role={inlineAction.state === "error" ? "alert" : "status"}
          aria-live="polite"
          className={
            "fixed bottom-6 left-1/2 z-[70] flex min-w-[360px] max-w-[min(720px,calc(100vw-2rem))] -translate-x-1/2 items-start gap-3 overflow-hidden rounded-2xl border px-4 py-3 text-sm shadow-[0_18px_50px_rgba(24,31,50,0.20)] " +
            (inlineAction.state === "error"
              ? "border-red-200 bg-red-50 text-red-700"
              : inlineAction.state === "success"
                ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                : "border-primary-200 bg-white text-primary-700")
          }
        >
          {inlineAction.state === "loading" && (
            <span className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-50" aria-hidden>
              <span className="absolute h-4 w-4 animate-ping rounded-full bg-primary-200 motion-reduce:animate-none" />
              <span className="relative h-2 w-2 rounded-full bg-primary-600" />
            </span>
          )}
          <div className="min-w-0 flex-1">
            <div className={inlineAction.state === "loading" && !streamingDraft ? "animate-pulse motion-reduce:animate-none" : ""}>
              {streamingDraft ? "AI đang viết bản đề xuất…" : inlineAction.message}
            </div>
            {inlineAction.state === "loading" && streamingDraft && (
              <div data-testid="streaming-rewrite-draft" className="mt-2 max-h-36 overflow-y-auto whitespace-pre-wrap rounded-xl bg-primary-50/70 px-3 py-2 text-sm leading-6 text-ink-800">
                {streamingDraft}<span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-primary-600 align-middle motion-reduce:animate-none" aria-hidden />
              </div>
            )}
          </div>
          {inlineAction.action === "reload_chapter" && (
            <button
              type="button"
              onClick={() => void reloadChapterFromServer()}
              className="ml-auto shrink-0 rounded-lg bg-red-700 px-3 py-1.5 font-semibold text-white hover:bg-red-800 active:translate-y-px"
            >
              Tải lại chương
            </button>
          )}
          {inlineAction.state !== "loading" && !inlineAction.action && (
            <button
              type="button"
              onClick={() => setInlineAction(null)}
              className="ml-4 shrink-0 rounded px-2 py-1 font-medium hover:bg-black/5 active:translate-y-px"
            >
              Đóng
            </button>
          )}
        </div>
      )}

      {activePendingEdit && typeof document !== "undefined" && createPortal(
        <aside
          aria-label="Duyệt đề xuất AI"
          className="fixed bottom-4 left-1/2 z-[95] w-[min(900px,calc(100vw-2rem))] -translate-x-1/2"
        >
          {activeReviewExpanded && (
            <div className="mb-2 max-h-[min(62vh,620px)] overflow-y-auto overscroll-contain rounded-2xl">
              <PendingEditRibbon
                edit={activePendingEdit}
                onAccept={handleAccept}
                onReject={handleReject}
                onRetry={activePendingEdit.source === "chat_rewrite" ? undefined : handleRetry}
                stale={staleIds.has(activePendingEdit.id)}
                busy={busyEditIds.has(activePendingEdit.id)}
              />
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-ink-200 bg-white/95 p-2.5 shadow-[0_18px_55px_rgba(24,31,50,0.20)] backdrop-blur">
            <span className="rounded-lg bg-primary-50 px-3 py-2 text-sm font-semibold capitalize text-primary-700">{(activePendingEdit.source || "AI edit").replace("_", " ")}</span>
            <button type="button" aria-expanded={activeReviewExpanded} onClick={() => setActiveReviewExpanded(value => !value)} className="rounded-lg px-3 py-2 text-sm font-semibold text-ink-700 hover:bg-ink-50">
              {activeReviewExpanded ? "Ẩn thay đổi" : "Xem thay đổi"}
            </button>
            <div className="ml-auto flex items-center gap-2">
              <button type="button" disabled={busyEditIds.has(activePendingEdit.id)} onClick={() => void handleReject(activePendingEdit.id)} className="rounded-lg px-3 py-2 text-sm font-semibold text-ink-600 hover:bg-red-50 hover:text-red-700 disabled:opacity-50">Bỏ</button>
              <button type="button" disabled={busyEditIds.has(activePendingEdit.id)} onClick={() => void handleAccept(activePendingEdit.id)} className="inline-flex items-center gap-1.5 rounded-xl bg-primary-600 px-4 py-2 text-sm font-semibold text-white hover:bg-primary-700 disabled:opacity-50"><Check className="h-4 w-4" />Chấp nhận</button>
              <button type="button" aria-label="Đóng thanh duyệt" onClick={() => setActivePendingEdit(null)} className="rounded-lg p-2 text-ink-400 hover:bg-ink-50 hover:text-ink-800"><X className="h-4 w-4" /></button>
            </div>
          </div>
        </aside>,
        document.body,
      )}

      {pendingEdits.length > 0 && (
        <section className="mt-8 space-y-4 border-t border-ink-100 pt-6" aria-label="AI edit proposals">
          <div className="flex items-center justify-between">
            <div><p className="text-sm font-semibold text-ink-900">AI edit proposals</p><p className="mt-0.5 text-xs text-ink-400">Review each change before it becomes part of the chapter.</p></div>
            <span className="rounded-md bg-primary-50 px-2 py-1 text-xs font-semibold tabular-nums text-primary-700">{pendingEdits.length}</span>
          </div>
          {pendingEdits.filter(edit => edit.id !== activePendingEdit?.id).map(edit => (
            <div key={edit.id}>
              <PendingEditRibbon
                edit={edit}
                onAccept={handleAccept}
                onReject={handleReject}
                onRetry={edit.source === "chat_rewrite" ? undefined : handleRetry}
                stale={staleIds.has(edit.id)}
                busy={busyEditIds.has(edit.id)}
              />
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
