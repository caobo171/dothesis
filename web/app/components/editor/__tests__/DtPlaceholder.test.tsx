import { describe, it, expect } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Markdown } from "tiptap-markdown";
import { DtPlaceholder, dtLabel } from "../extensions/DtPlaceholder";


function Harness({ content }: { content: string }) {
  const editor = useEditor({
    extensions: [StarterKit, Markdown.configure({ html: false }), DtPlaceholder],
    content,
    immediatelyRender: true,
  });
  if (!editor) return null;
  return <EditorContent editor={editor} />;
}


describe("DtPlaceholder", () => {
  it("maps known kinds to a friendly label and humanizes unknown ones", () => {
    expect(dtLabel("data_cleaning")).toBe("Tóm tắt sàng lọc dữ liệu");
    expect(dtLabel("some_new_kind")).toBe("some new kind");
  });

  it("decorates a [[DT:kind]] paragraph with the label", async () => {
    const { container } = render(<Harness content={"[[DT:data_cleaning]]"} />);
    await waitFor(() => {
      const el = container.querySelector(".dt-token");
      expect(el).toBeTruthy();
      expect(el?.getAttribute("data-dt-label")).toBe("Tóm tắt sàng lọc dữ liệu");
    });
  });

  it("does not decorate ordinary paragraphs", async () => {
    const { container } = render(<Harness content={"Just normal prose."} />);
    await new Promise(r => setTimeout(r, 10));
    expect(container.querySelector(".dt-token")).toBeNull();
  });
});
