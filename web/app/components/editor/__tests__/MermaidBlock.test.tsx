import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Markdown } from "tiptap-markdown";
import { MermaidBlock } from "../extensions/MermaidBlock";


// mermaid touches real layout APIs jsdom doesn't have, so we mock the module —
// the extension's job is to call it with the source and inject the returned SVG,
// which is exactly what we assert.
const renderSpy = vi.fn(async (_id: string, src: string) => ({
  svg: `<svg data-src="${(src ?? "").trim()}">diagram</svg>`,
}));
vi.mock("mermaid", () => ({
  default: { initialize: vi.fn(), render: (...args: any[]) => renderSpy(args[0], args[1]) },
}));


function Harness({ content }: { content: string }) {
  const editor = useEditor({
    extensions: [StarterKit.configure({ codeBlock: false }), Markdown.configure({ html: false }), MermaidBlock],
    content,
    immediatelyRender: true,
  });
  if (!editor) return null;
  return <EditorContent editor={editor} />;
}


beforeEach(() => renderSpy.mockClear());
afterEach(() => vi.restoreAllMocks());


describe("MermaidBlock", () => {
  it("renders a live diagram preview for a ```mermaid block", async () => {
    render(<Harness content={"```mermaid\ngraph TD;\n  A-->B;\n```"} />);
    // The mermaid renderer is invoked with the block source...
    await waitFor(() => expect(renderSpy).toHaveBeenCalled());
    expect(renderSpy.mock.calls[0][1]).toContain("graph TD;");
    // ...and the returned SVG is injected into the preview.
    await waitFor(() => expect(screen.getByLabelText("Sơ đồ mermaid")).toBeInTheDocument());
  });

  it("does not render a diagram for a non-mermaid code block", async () => {
    render(<Harness content={"```js\nconst x = 1;\n```"} />);
    // Give any effect a tick; the renderer must never be called for plain code.
    await new Promise(r => setTimeout(r, 10));
    expect(renderSpy).not.toHaveBeenCalled();
  });
});
