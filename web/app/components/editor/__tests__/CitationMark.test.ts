import { describe, it, expect } from "vitest";
import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { CitationMark } from "../extensions/CitationMark";


describe("CitationMark", () => {
  it("renders with data-ref attribute", () => {
    const editor = new Editor({ extensions: [StarterKit, CitationMark], content: "<p>See it.</p>" });
    editor.commands.setTextSelection({ from: 1, to: 4 }); // "See"
    editor.commands.setMark("citation", { referenceId: "ref-abc" });
    expect(editor.getHTML()).toContain('data-ref="ref-abc"');
    expect(editor.getHTML()).toContain('class="citation"');
  });

  it("round-trips through HTML", () => {
    const html = '<p>x <span data-ref="r1" class="citation">(Smith, 2024)</span></p>';
    const editor = new Editor({ extensions: [StarterKit, CitationMark], content: html });
    expect(editor.getHTML()).toContain('data-ref="r1"');
  });
});
