import { describe, expect, it } from "vitest";
import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { Markdown } from "tiptap-markdown";
import { AiProcessing } from "../extensions/AiProcessing";


describe("AiProcessing mark", () => {
  it("highlights a range without changing serialized markdown", () => {
    const editor = new Editor({
      extensions: [StarterKit, Markdown.configure({ html: false }), AiProcessing],
      content: "<p>Selected passage</p>",
    });
    const before = editor.storage.markdown.getMarkdown();
    const mark = editor.schema.marks.aiProcessing;
    editor.view.dispatch(editor.state.tr.addMark(1, 9, mark.create()));
    expect(editor.getHTML()).toContain('data-ai-processing="true"');
    expect(editor.getHTML()).toContain('class="ai-processing"');
    expect(editor.storage.markdown.getMarkdown()).toBe(before);
  });
});
