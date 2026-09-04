import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { useState } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Table, TableRow, TableHeader, TableCell } from "@tiptap/extension-table";
import { Markdown } from "tiptap-markdown";
import { EditorToolbar } from "../EditorToolbar";


// The toolbar moved out of ChapterEditor (chapters now stack on one page under
// a single shared toolbar), so we exercise it against a minimal live editor.
function Harness({ content = "Hello world." }: { content?: string }) {
  const [font, setFont] = useState({ family: "serif", size: 16 });
  const editor = useEditor({
    extensions: [
      StarterKit, Markdown.configure({ html: false }),
      Table.configure({ resizable: true }), TableRow, TableHeader, TableCell,
    ],
    content,
    immediatelyRender: true,
  });
  if (!editor) return null;
  return (
    <>
      <EditorToolbar
        editor={editor}
        fontFamily={font.family}
        fontSize={font.size}
        onFontFamily={family => setFont(f => ({ ...f, family }))}
        onFontSize={size => setFont(f => ({ ...f, size }))}
      />
      <EditorContent editor={editor} />
    </>
  );
}

afterEach(() => vi.restoreAllMocks());


describe("EditorToolbar", () => {
  it("renders the formatting toolbar with the core controls", async () => {
    render(<Harness />);
    expect(await screen.findByRole("toolbar", { name: "Định dạng" })).toBeInTheDocument();
    expect(screen.getByLabelText("Đậm")).toBeInTheDocument();
    expect(screen.getByLabelText("Phông chữ")).toBeInTheDocument();
    expect(screen.getByLabelText("Cỡ chữ")).toBeInTheDocument();
    expect(screen.getByLabelText("Kiểu văn bản")).toBeInTheDocument();
  });

  it("shows a live word count", async () => {
    render(<Harness content="Hello world." />);
    await waitFor(() => expect(screen.getByLabelText("Số từ")).toHaveTextContent("2 từ"));
  });

  it("steps the font size", async () => {
    render(<Harness />);
    const size = (await screen.findByLabelText("Cỡ chữ")) as HTMLInputElement;
    expect(size.value).toBe("16");
    fireEvent.click(screen.getByLabelText("Tăng cỡ chữ"));
    await waitFor(() => expect(size.value).toBe("17"));
  });

  it("toggles bold via the toolbar button", async () => {
    render(<Harness />);
    const bold = await screen.findByLabelText("Đậm");
    expect(bold).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(bold);
    await waitFor(() => expect(bold).toHaveAttribute("aria-pressed", "true"));
  });

  it("inserts a table via the toolbar button", async () => {
    const { container } = render(<Harness content="Body." />);
    fireEvent.click(await screen.findByLabelText("Chèn bảng"));
    await waitFor(() => expect(container.querySelector("table")).toBeTruthy());
  });
});
