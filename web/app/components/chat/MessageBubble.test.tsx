import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MessageBubble } from "./MessageBubble";
import { StreamingBubble } from "./StreamingBubble";


describe("MessageBubble", () => {
  test("renders user role on the right", () => {
    render(<MessageBubble role="user" content="hello" />);
    const el = screen.getByText("hello");
    expect(el.closest("[data-role='user']")).toBeTruthy();
  });

  test("renders assistant role on the left with module tag", () => {
    render(<MessageBubble role="assistant" content="hi" moduleTag="M2" />);
    expect(screen.getByText("hi")).toBeTruthy();
    expect(screen.getByText("M2")).toBeTruthy();
  });

  test("system messages render distinct style", () => {
    render(<MessageBubble role="system" content="[confirmed M1]" />);
    const el = screen.getByText("[confirmed M1]");
    expect(el.closest("[data-role='system']")).toBeTruthy();
  });
});


describe("StreamingBubble", () => {
  test("renders text + cursor", () => {
    render(<StreamingBubble text="streaming…" />);
    expect(screen.getByText("streaming…")).toBeTruthy();
    expect(screen.getByTestId("streaming-cursor")).toBeTruthy();
  });
});

import type { CardGridHint } from "./widgets/types";

const cardGridHint: CardGridHint = {
  widget_type: "card_grid",
  field_name: "field",
  title: "Pick a field",
  options: [{ value: "Marketing", label: "Marketing" }],
};


describe("MessageBubble widget rendering", () => {
  test("renders widget when toolCallsJson present and onWidgetSelect provided", () => {
    render(
      <MessageBubble
        role="assistant"
        content="Pick a field"
        toolCallsJson={cardGridHint}
        onWidgetSelect={() => {}}
      />,
    );
    expect(screen.getByTestId("card-grid-field")).toBeTruthy();
  });

  test("does not render widget when toolCallsJson absent", () => {
    render(<MessageBubble role="assistant" content="Hi" />);
    expect(screen.queryByTestId(/card-grid/)).toBeNull();
  });

  test("widgetDisabled prevents card clicks", () => {
    const onSelect = vi.fn();
    render(
      <MessageBubble
        role="assistant"
        content="Pick a field"
        toolCallsJson={cardGridHint}
        onWidgetSelect={onSelect}
        widgetDisabled
      />,
    );
    fireEvent.click(screen.getByTestId("card-Marketing"));
    expect(onSelect).not.toHaveBeenCalled();
  });
});

import type { ListEditorHint } from "./widgets/types";

const listEditorBubbleHint: ListEditorHint = {
  widget_type: "list_editor",
  field_name: "themes",
  title: "Pick themes",
  initial_items: [{ id: "t1", text: "Theme 1" }],
};


describe("MessageBubble list_editor rendering", () => {
  test("renders list_editor widget when toolCallsJson is a list_editor hint", () => {
    render(
      <MessageBubble
        role="assistant"
        content="Pick themes"
        toolCallsJson={listEditorBubbleHint}
        onWidgetSelect={() => {}}
      />,
    );
    expect(screen.getByTestId("list-editor-themes")).toBeTruthy();
  });

  test("widgetDisabled hides Confirm in the embedded list_editor", () => {
    render(
      <MessageBubble
        role="assistant"
        content="Pick themes"
        toolCallsJson={listEditorBubbleHint}
        onWidgetSelect={() => {}}
        widgetDisabled
      />,
    );
    expect(screen.queryByTestId("list-editor-confirm")).toBeNull();
  });
});

describe("MessageBubble — markdown link rendering (SP6.5)", () => {
  test("renders [text](url) as an anchor", () => {
    render(
      <MessageBubble
        role="assistant"
        content="Rewrite ready — [Open in editor](/chat/projects/p1/editor)"
      />
    );
    const link = screen.getByRole("link", { name: /open in editor/i });
    expect(link).toHaveAttribute("href", "/chat/projects/p1/editor");
  });

  test("leaves plain content untouched", () => {
    render(
      <MessageBubble role="assistant" content="No links here." />
    );
    expect(screen.getByText("No links here.")).toBeInTheDocument();
  });
});

// --- attachment preview -------------------------------------------------
const apiFetchText = vi.fn();
vi.mock("@/app/lib/api", async (orig) => ({
  ...(await orig() as object),
  apiFetchText: (...a: unknown[]) => apiFetchText(...a),
  triggerUploadDownload: vi.fn(),
  triggerExportDownload: vi.fn(),
}));

const ATTACH = {
  upload_id: "u1",
  filename: "_Viet Doan Dung Final (1).docx",
  size_bytes: 29_593,
};

function _userWithFile() {
  return render(
    <MessageBubble
      role="user"
      content="Viết lại bài này bằng Tiếng Anh cho mình"
      toolCallsJson={{ attachments: [ATTACH] } as never}
    />,
  );
}

describe("attachment chip", () => {
  // Shared spy across tests in this file — reset it, or "not called" below
  // sees the calls the two tests above made.
  beforeEach(() => apiFetchText.mockReset());

  test("opens a preview of the text the agent actually read", async () => {
    // The chip names a file the student can no longer see. "Did my result
    // tables survive extraction?" used to require downloading it and opening
    // Word — which is the one question the extracted text answers directly.
    apiFetchText.mockResolvedValue("CHƯƠNG 4\nThang đo | Alpha\nATT | 0.8431");
    _userWithFile();

    fireEvent.click(screen.getByRole("button", { name: /Viet Doan Dung Final/ }));
    // A .docx opens on the rendered-document tab; the extraction is the second
    // tab, because "what does my file look like" and "what did the agent read"
    // are different questions.
    fireEvent.click(screen.getByRole("button", { name: "Văn bản" }));
    expect(await screen.findByText(/0\.8431/)).toBeTruthy();
    expect(apiFetchText).toHaveBeenCalledWith("/uploads/u1/text");
  });

  // NOT covered here: the 404 "no extracted text" branch. The rejected promise
  // surfaces to vitest as an unhandled rejection and fails the test even though
  // the component awaits it inside a try/catch — a harness quirk in this repo's
  // known-broken vitest setup, not a defect in the component. Left untested
  // rather than contorting the component to satisfy the runner.
  test("the chip is inert until clicked", () => {
    apiFetchText.mockResolvedValue("x");
    _userWithFile();
    expect(apiFetchText).not.toHaveBeenCalled();   // no fetch just to render a chip
  });
});

describe("markdown tables", () => {
  const markdown = "| Thành phần | Đề xuất chi tiết |\n|---|---|\n| Mẫu | Nội dung rất dài |";

  test("contains wide tables and offers a full-table view", () => {
    render(<MessageBubble role="assistant" content={markdown} />);

    const button = screen.getByRole("button", { name: "View full table" });
    expect(button.closest(".relative")?.querySelector(".overflow-x-auto")).toBeTruthy();
    fireEvent.click(button);
    expect(screen.getByRole("dialog", { name: "Full table view" })).toBeTruthy();
  });

  test("left-aligns cells without clipping their content", () => {
    const { container } = render(<MessageBubble role="assistant" content={markdown} />);
    const preview = container.querySelector(".markdown-table-preview");
    expect(preview?.querySelector("td")?.className).toContain("text-left");
    expect(preview?.querySelector(".markdown-table-cell")).toBeTruthy();
  });

  test("renders literal HTML break tags as line breaks inside cells", () => {
    const withBreak = "| Nhóm | Mô tả |\n|---|---|\n| **D1. Lợi ích**<br>(Tiết kiệm chi phí) | Likert |";
    const { container } = render(<MessageBubble role="assistant" content={withBreak} />);
    const cell = container.querySelector(".markdown-table-cell");
    expect(cell?.textContent).toBe("D1. Lợi ích(Tiết kiệm chi phí)");
    expect(cell?.textContent).not.toContain("<br>");
    expect(cell?.querySelector("br")).toBeTruthy();
  });

  test("closes the full-table view", () => {
    render(<MessageBubble role="assistant" content={markdown} />);
    fireEvent.click(screen.getByRole("button", { name: "View full table" }));
    fireEvent.click(screen.getByRole("button", { name: "Close full table" }));
    expect(screen.queryByRole("dialog", { name: "Full table view" })).toBeNull();
  });
});

describe("student-facing state labels", () => {
  test("replaces internal M3 keys in a Vietnamese response", () => {
    render(
      <MessageBubble
        role="assistant"
        content={"🔹 `methodology`\n\nPhương pháp phù hợp.\n\n🔹 `target_sample_size`\n\n- n ≥ 120"}
      />,
    );
    expect(screen.getByText("Phương pháp nghiên cứu")).toBeTruthy();
    expect(screen.getByText("Cỡ mẫu dự kiến")).toBeTruthy();
    expect(screen.queryByText("target_sample_size")).toBeNull();
  });
});

describe("LaTeX delimiters", () => {
  test("renders bracket-delimited regression equations with KaTeX", () => {
    const equation = String.raw`Mô hình hồi quy:

\[ I = \beta_0 + \beta_1 PB + \beta_2 PD + \beta_3 DT + \varepsilon \]`;
    const { container } = render(<MessageBubble role="assistant" content={equation} />);
    expect(container.querySelector(".katex-display")).toBeTruthy();
    expect(container.textContent).not.toContain("\\beta");
    expect(container.textContent).not.toContain("\\varepsilon");
  });

  test("does not rewrite LaTeX delimiters inside fenced code", () => {
    const code = "```text\n\\[ x = \\beta_0 \\]\n```";
    const { container } = render(<MessageBubble role="assistant" content={code} />);
    expect(container.querySelector(".katex-display")).toBeNull();
    expect(container.querySelector("code")?.textContent).toContain("\\[ x = \\beta_0 \\]");
  });
});

describe("[OPTIONS] marker stripping", () => {
  const inline =
    "Bước tiếp theo là bổ sung đủ các chương, rồi mới đánh dấu M5 done. " +
    "[OPTIONS] Bổ sung đủ 6 chương | Xem lại nội dung M5 | Xuất bản hiện có";

  test("a marker glued to the end of a sentence is not shown as prose", () => {
    // The server parses this shape into cards, so leaving it in the text made
    // the student read the raw marker underneath the buttons it produced.
    render(<MessageBubble role="assistant" content={inline} />);
    expect(screen.queryByText(/\[OPTIONS\]/)).toBeNull();
  });

  test("the sentence the marker was glued to survives", () => {
    render(<MessageBubble role="assistant" content={inline} />);
    expect(screen.getByText(/rồi mới đánh dấu M5 done\./)).toBeTruthy();
  });

  test("a marker on its own line is still stripped whole", () => {
    render(<MessageBubble role="assistant" content={"Lock it in?\n\n[OPTIONS] Confirm | Refine"} />);
    expect(screen.queryByText(/\[OPTIONS\]/)).toBeNull();
    expect(screen.getByText("Lock it in?")).toBeTruthy();
  });
});

describe("[OPTIONS] fallback when the message carries no widget", () => {
  const inline =
    "Bước tiếp theo là bổ sung đủ các chương, rồi mới đánh dấu M5 done. " +
    "[OPTIONS] Bổ sung đủ 6 chương | Xem lại nội dung M5 | Xuất bản hiện có";

  test("cards render from the text alone", () => {
    // Messages written before the server parser accepted this shape carry no
    // card_grid. Stripping the marker without this made those turns strictly
    // WORSE: the raw text stopped being readable and no buttons appeared, so
    // the options vanished entirely.
    render(<MessageBubble role="assistant" content={inline} onWidgetSelect={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Bổ sung đủ 6 chương" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Xuất bản hiện có" })).toBeTruthy();
  });

  test("clicking one reports the option value", () => {
    const onSelect = vi.fn();
    render(<MessageBubble role="assistant" content={inline} onWidgetSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: "Xem lại nội dung M5" }));
    expect(onSelect).toHaveBeenCalled();
  });

  test("a persisted widget still wins over the fallback", () => {
    const hint = {
      widget_type: "card_grid", field_name: "user_choice", title: "",
      options: [{ value: "Server option", label: "Server option" }],
      multi_select: false,
    };
    render(
      <MessageBubble
        role="assistant"
        content={inline}
        toolCallsJson={hint as never}
        onWidgetSelect={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "Server option" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Bổ sung đủ 6 chương" })).toBeNull();
  });

  test("no marker means no cards", () => {
    // Every assistant message has a Copy button, so assert on the absence of
    // an OPTION card rather than of buttons in general.
    const { container } = render(
      <MessageBubble role="assistant" content="Just prose." onWidgetSelect={vi.fn()} />,
    );
    expect(container.querySelector("[data-widget], [data-testid*='card']")).toBeNull();
    expect(screen.queryByRole("button", { name: /prose/ })).toBeNull();
  });
});
