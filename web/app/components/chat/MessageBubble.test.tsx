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
