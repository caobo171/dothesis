import { describe, it, expect } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { Editor } from "@tiptap/core";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Markdown } from "tiptap-markdown";
import { CitationHighlight } from "../extensions/CitationHighlight";


function Harness({ content }: { content: string }) {
  const editor = useEditor({
    extensions: [StarterKit, Markdown.configure({ html: false }), CitationHighlight],
    content,
    immediatelyRender: true,
  });
  if (!editor) return null;
  return <EditorContent editor={editor} />;
}


describe("CitationHighlight", () => {
  it("highlights a parenthetical citation", async () => {
    const { container } = render(<Harness content="Short-form video reduces focus (Liem et al., 2024)." />);
    await waitFor(() => {
      const marks = container.querySelectorAll(".citation-auto");
      expect(marks.length).toBeGreaterThanOrEqual(1);
      expect(Array.from(marks).some(m => m.textContent?.includes("Liem et al., 2024"))).toBe(true);
    });
  });

  it("highlights each citation in a multi-reference parenthetical", async () => {
    const { container } = render(<Harness content="Prior work (H.A et al., 2019; Cham et al., 2024) agrees." />);
    await waitFor(() => {
      const el = container.querySelector(".citation-auto");
      expect(el?.textContent).toContain("2019");
      expect(el?.textContent).toContain("Cham et al., 2024");
    });
  });

  it("highlights a narrative citation (Author (Year))", async () => {
    const { container } = render(<Harness content="As Cham et al. (2024) show, engagement drops." />);
    await waitFor(() => {
      const marks = Array.from(container.querySelectorAll(".citation-auto"));
      expect(marks.some(m => m.textContent?.includes("Cham et al. (2024)"))).toBe(true);
    });
  });

  it("does not highlight a plain parenthetical without a year", async () => {
    const { container } = render(<Harness content="This is important (see the appendix)." />);
    await new Promise(r => setTimeout(r, 10));
    expect(container.querySelector(".citation-auto")).toBeNull();
  });

  it("is decoration-only — the stored markdown is unchanged", () => {
    const src = "Focus drops (Liem et al., 2024).";
    const editor = new Editor({
      extensions: [StarterKit, Markdown.configure({ html: false }), CitationHighlight],
      content: src,
    });
    const md = editor.storage.markdown.getMarkdown();
    expect(md).toContain("(Liem et al., 2024)");
    expect(md).not.toContain("citation-auto");
  });
});
