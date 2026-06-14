import { describe, it, expect } from "vitest";
import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { Markdown } from "tiptap-markdown";

import { CitationMark } from "../extensions/CitationMark";
import { AiPending } from "../extensions/AiPending";


// Guards export quality: the editor stores `editor.storage.markdown.getMarkdown()`,
// which the M5 exporter consumes. These assert the load -> serialize cycle keeps
// the stored prose as the same markdown dialect (headings stay `##`, custom
// editor-only marks never leak syntax into the export).
function mkEditor(markdown: string) {
  return new Editor({
    extensions: [StarterKit, Markdown.configure({ html: false }), AiPending, CitationMark],
    content: markdown,
  });
}

describe("markdown round-trip (export safety)", () => {
  it("preserves headings as markdown, not literal text or HTML", () => {
    const editor = mkEditor("## 1.1 Background and Motivation\n\nSome prose.");
    // Renders as a real heading node...
    expect(editor.getHTML()).toContain("<h2>1.1 Background and Motivation</h2>");
    // ...and serializes back to the same markdown the exporter expects.
    const md = editor.storage.markdown.getMarkdown();
    expect(md).toContain("## 1.1 Background and Motivation");
    expect(md).toContain("Some prose.");
  });

  it("serializes a citation mark to its bare text (no span / no data-ref)", () => {
    const editor = mkEditor("Stand-up comedy (Attardo, 2014).");
    editor.commands.setTextSelection({ from: 18, to: 32 }); // "(Attardo, 2014)"
    editor.commands.setMark("citation", { referenceId: "ref-1" });
    const md = editor.storage.markdown.getMarkdown();
    expect(md).toContain("(Attardo, 2014)");
    expect(md).not.toContain("data-ref");
    expect(md).not.toContain("<span");
  });

  it("serializes a pending-edit highlight to plain text", () => {
    const editor = mkEditor("This is draft text.");
    editor.commands.setTextSelection({ from: 1, to: 5 }); // "This"
    editor.commands.setMark("aiPending", {
      pendingId: "p1", source: "paraphrase", oldText: "This", newText: "That",
    });
    const md = editor.storage.markdown.getMarkdown();
    expect(md).toBe("This is draft text.");
    expect(md).not.toContain("data-pending-id");
  });
});
