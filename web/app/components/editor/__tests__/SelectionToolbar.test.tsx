import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SelectionToolbar } from "../SelectionToolbar";

const noop = () => {};
const handlers = () => ({
  onRewrite: noop, onTranslate: noop, onCite: noop,
});


describe("SelectionToolbar", () => {
  it("shows the bar: Ask AI + Translate + Cite, with rewrites hidden until opened", () => {
    render(<SelectionToolbar {...handlers()} />);
    expect(screen.getByRole("button", { name: /ask ai/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /translate/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cite/i })).toBeInTheDocument();
    // Rewrite actions live in the dropdown — not rendered until it opens.
    expect(screen.queryByRole("menuitem", { name: /paraphrase/i })).toBeNull();
  });

  it("opens the Ask AI dropdown to reveal the rewrite actions", () => {
    render(<SelectionToolbar {...handlers()} />);
    fireEvent.click(screen.getByRole("button", { name: /ask ai/i }));
    for (const name of [/paraphrase/i, /improve/i, /proofread/i, /humanize/i, /expand/i, /shorten/i]) {
      expect(screen.getByRole("menuitem", { name })).toBeInTheDocument();
    }
  });

  it("portals and flips the dropdown above the toolbar near the viewport bottom", () => {
    const rect = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      x: 120, y: 700, left: 120, top: 700, right: 220, bottom: 736,
      width: 100, height: 36, toJSON: () => ({}),
    } as DOMRect);
    render(<SelectionToolbar {...handlers()} />);
    fireEvent.click(screen.getByRole("button", { name: /ask ai/i }));
    const menu = screen.getByRole("menu");
    expect(menu).toHaveAttribute("data-placement", "top");
    expect(menu.parentElement).toBe(document.body);
    expect(menu).toHaveClass("fixed");
    rect.mockRestore();
  });

  it("uses rewrite actions as editable prompt presets and submits the edited instruction", () => {
    const onRewrite = vi.fn();
    render(<SelectionToolbar {...handlers()} onRewrite={onRewrite} />);
    fireEvent.click(screen.getByRole("button", { name: /ask ai/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: /expand/i }));
    expect(onRewrite).not.toHaveBeenCalled();
    const prompt = screen.getByLabelText(/chỉnh đoạn này/i);
    expect((prompt as HTMLTextAreaElement).value).toMatch(/mở rộng/i);
    fireEvent.change(prompt, { target: { value: "Mở rộng và thêm một ví dụ thực tế." } });
    fireEvent.click(screen.getByRole("button", { name: /tạo đề xuất/i }));
    expect(onRewrite).toHaveBeenCalledWith("expand", "Mở rộng và thêm một ví dụ thực tế.");
  });

  it.each([
    ["onTranslate", /translate/i],
    ["onCite", /cite/i],
  ] as const)("fires %s directly from the bar", (prop, name) => {
    const fn = vi.fn();
    render(<SelectionToolbar {...handlers()} {...{ [prop]: fn }} />);
    fireEvent.click(screen.getByRole("button", { name }));
    expect(fn).toHaveBeenCalledTimes(1);
  });
});
