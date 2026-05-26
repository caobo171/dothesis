import { describe, expect, test, vi } from "vitest";
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
