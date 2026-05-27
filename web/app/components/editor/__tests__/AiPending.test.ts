import { describe, it, expect } from "vitest";
import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { AiPending } from "../extensions/AiPending";


function makeEditor(content = "<p>Hello world</p>") {
  return new Editor({ extensions: [StarterKit, AiPending], content });
}


describe("AiPending mark", () => {
  it("can be applied to a range and serializes attrs", () => {
    const editor = makeEditor();
    editor.commands.setTextSelection({ from: 1, to: 6 }); // "Hello"
    editor.commands.setMark("aiPending", {
      pendingId: "edit-1",
      source: "paraphrase",
      oldText: "Hello",
      newText: "Greetings",
    });
    const html = editor.getHTML();
    expect(html).toContain('data-pending-id="edit-1"');
    expect(html).toContain('data-source="paraphrase"');
    expect(html).toContain('data-old-text="Hello"');
    expect(html).toContain('class="ai-pending"');
  });

  it("can be removed by id", () => {
    const editor = makeEditor();
    editor.commands.setTextSelection({ from: 1, to: 6 });
    editor.commands.setMark("aiPending", {
      pendingId: "edit-1", source: "paraphrase",
      oldText: "Hello", newText: "Greetings",
    });
    editor.commands.unsetMark("aiPending");
    expect(editor.getHTML()).not.toContain("data-pending-id");
  });

  it("parses from HTML round-trip", () => {
    const html = '<p>x <span data-pending-id="e1" data-source="cite" data-old-text="" data-new-text=" (S, 2024)" class="ai-pending"> (S, 2024)</span></p>';
    const editor = new Editor({ extensions: [StarterKit, AiPending], content: html });
    expect(editor.getHTML()).toContain('data-pending-id="e1"');
  });
});
