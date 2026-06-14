import { describe, it, expect } from "vitest";
import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { Markdown } from "tiptap-markdown";

import { CitationMark } from "../extensions/CitationMark";
import { AiPending } from "../extensions/AiPending";
import { buildOffsetMap, offsetToPos, posToOffset } from "../markdownOffset";


function mkEditor(markdown: string) {
  return new Editor({
    extensions: [StarterKit, Markdown.configure({ html: false }), AiPending, CitationMark],
    content: markdown,
  });
}

describe("markdownOffset — markdown char offset <-> PM position", () => {
  it("maps an offset inside the body paragraph (past a heading) to the right text", () => {
    const md = "## Heading\n\nStand-up comedy is great.";
    const editor = mkEditor(md);
    const map = buildOffsetMap(editor);
    const docSize = editor.state.doc.content.size;

    // Offset of "comedy" in the markdown string.
    const start = md.indexOf("comedy");
    const from = offsetToPos(map, docSize, start);
    const to = offsetToPos(map, docSize, start + "comedy".length);
    expect(editor.state.doc.textBetween(from, to)).toBe("comedy");
  });

  it("round-trips PM position -> offset -> PM position", () => {
    const editor = mkEditor("## Background\n\nAlpha beta gamma.\n\nSecond para here.");
    const map = buildOffsetMap(editor);
    const docSize = editor.state.doc.content.size;

    // Pick a position inside "gamma".
    const md = map.md;
    const pos = offsetToPos(map, docSize, md.indexOf("gamma") + 2);
    const offset = posToOffset(map, pos);
    expect(offsetToPos(map, docSize, offset)).toBe(pos);
  });

  it("a selection's offsets slice the markdown to the selected text (server splice contract)", () => {
    const editor = mkEditor("## Intro\n\nThe quick brown fox.");
    const map = buildOffsetMap(editor);
    const docSize = editor.state.doc.content.size;

    // Simulate selecting "quick brown" in the doc.
    const md = map.md;
    const selFrom = offsetToPos(map, docSize, md.indexOf("quick"));
    const selTo = offsetToPos(map, docSize, md.indexOf("quick") + "quick brown".length);

    const fromOffset = posToOffset(map, selFrom);
    const toOffset = posToOffset(map, selTo);
    // This is exactly what the server does: prose[from:to].
    expect(md.slice(fromOffset, toOffset)).toBe("quick brown");
  });

  it("maps offset 0 to the start of the first text run even when prose opens with a heading", () => {
    const editor = mkEditor("## 1.1 Background\n\nBody.");
    const map = buildOffsetMap(editor);
    const docSize = editor.state.doc.content.size;
    const pos = offsetToPos(map, docSize, 0);
    // First text node is "1.1 Background" — its PM start, not inside "## ".
    expect(editor.state.doc.textBetween(pos, pos + 3)).toBe("1.1");
  });

  it("maps a whole-chapter range (chat_rewrite: 0..len) across the full doc", () => {
    const md = "## A\n\nFirst.\n\nSecond.";
    const editor = mkEditor(md);
    const map = buildOffsetMap(editor);
    const docSize = editor.state.doc.content.size;
    const from = offsetToPos(map, docSize, 0);
    const to = offsetToPos(map, docSize, md.length);
    expect(from).toBeLessThan(to);
    expect(to).toBeLessThanOrEqual(docSize);
    // The mapped range spans from the first text run through the last.
    const covered = editor.state.doc.textBetween(from, to, " ");
    expect(covered).toContain("First.");
    expect(covered).toContain("Second.");
  });
});
