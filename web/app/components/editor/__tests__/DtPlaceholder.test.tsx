import { describe, it, expect } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Markdown } from "tiptap-markdown";
import { DtPlaceholder, dtLabel } from "../extensions/DtPlaceholder";


function Harness({ content, available = [] }: { content: string; available?: string[] }) {
  const editor = useEditor({
    extensions: [StarterKit, Markdown.configure({ html: false }),
      DtPlaceholder.configure({ availableKinds: available })],
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
      expect(el?.getAttribute("data-dt-prefix")).toContain("thiếu dữ liệu kiểm chứng");
      expect(el?.classList.contains("dt-token-unavailable")).toBe(true);
    });
  });

  it("promises export generation only when the verified block is available", async () => {
    const { container } = render(
      <Harness content={"[[DT:data_cleaning]]"} available={["data_cleaning"]} />,
    );
    await waitFor(() => {
      const el = container.querySelector(".dt-token");
      expect(el?.getAttribute("data-dt-prefix")).toContain("Tạo tự động khi export");
      expect(el?.classList.contains("dt-token-unavailable")).toBe(false);
    });
  });

  it("does not decorate ordinary paragraphs", async () => {
    const { container } = render(<Harness content={"Just normal prose."} />);
    await new Promise(r => setTimeout(r, 10));
    expect(container.querySelector(".dt-token")).toBeNull();
  });
});
