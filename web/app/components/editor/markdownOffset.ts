import type { Editor } from "@tiptap/core";


// Maps between character offsets in the serialized markdown (what the server
// stores as chapter.prose and slices for accept/splice in m5_editor.py) and
// ProseMirror document positions (what the editor's selection + marks use).
//
// Why this is non-trivial: markdown syntax — "## " before a heading, "**"
// around bold, the blank line between blocks, escape backslashes — lives only
// in the serialized string, never in the doc's text content. A position-based
// "+1" mapping (the old single-block assumption) drifts by 2 per block boundary
// and by the width of every syntax run, so it landed pending-edit highlights and
// splice ranges in the wrong place once chapters became real markdown.
//
// Both directions resolve against editor.storage.markdown.getMarkdown() — the
// exact string the autosave persists — so a client offset and the server's
// prose[from:to] always reference the same characters.
export type OffsetMap = {
  md: string;
  // Text runs in document order. Each maps a contiguous PM text range
  // [pmFrom, pmFrom+len) to its starting char offset in `md`.
  segments: { pmFrom: number; len: number; mdFrom: number }[];
};


// Align text nodes (in doc order) against the markdown via a forward-only
// cursor: each node's verbatim text is located after the previous match, so
// interleaved syntax characters are skipped automatically. Unalignable nodes
// (e.g. heavily escaped text) are dropped — callers clamp gracefully.
export function buildOffsetMap(editor: Editor): OffsetMap {
  const md: string = editor.storage.markdown.getMarkdown();
  const segments: OffsetMap["segments"] = [];
  let cursor = 0;
  editor.state.doc.descendants((node, pos) => {
    if (!node.isText || !node.text) return;
    const idx = md.indexOf(node.text, cursor);
    if (idx === -1) return;
    segments.push({ pmFrom: pos, len: node.text.length, mdFrom: idx });
    cursor = idx + node.text.length;
  });
  return { md, segments };
}


// markdown char offset -> PM position. Offsets that fall inside a syntax gap
// snap to the start of the following text run; offsets past all text resolve to
// the end of the doc.
export function offsetToPos(map: OffsetMap, docSize: number, offset: number): number {
  for (const s of map.segments) {
    if (offset <= s.mdFrom + s.len) {
      const within = Math.max(0, offset - s.mdFrom);
      return s.pmFrom + Math.min(within, s.len);
    }
  }
  return docSize;
}


// PM position -> markdown char offset (inverse of offsetToPos).
export function posToOffset(map: OffsetMap, pos: number): number {
  for (const s of map.segments) {
    if (pos <= s.pmFrom + s.len) {
      const within = Math.max(0, pos - s.pmFrom);
      return s.mdFrom + Math.min(within, s.len);
    }
  }
  return map.md.length;
}
