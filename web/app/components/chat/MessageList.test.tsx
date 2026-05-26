import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MessageList } from "./MessageList";


describe("MessageList", () => {
  test("renders all messages", () => {
    const messages = [
      { id: 1, role: "user" as const, content: "Hello", created_at: "2026-05-27" },
      { id: 2, role: "assistant" as const, content: "Hi back", created_at: "2026-05-27", module_tag: "M1" },
    ];
    render(<MessageList messages={messages} streamingText="" streamingModuleTag={null} />);
    expect(screen.getByText("Hello")).toBeTruthy();
    expect(screen.getByText("Hi back")).toBeTruthy();
    expect(screen.getByText("M1")).toBeTruthy();
  });

  test("renders streaming bubble when streamingText set", () => {
    render(<MessageList messages={[]} streamingText="streaming reply" streamingModuleTag="M2" />);
    expect(screen.getByText("streaming reply")).toBeTruthy();
    expect(screen.getByText("M2")).toBeTruthy();
  });
});

import type { CardGridHint } from "./widgets/types";

const hint: CardGridHint = {
  widget_type: "card_grid",
  field_name: "field",
  title: "Pick",
  options: [{ value: "Marketing", label: "Marketing" }],
};


describe("MessageList widget integration", () => {
  test("widget on the LAST assistant message is enabled", () => {
    const messages = [
      { id: 1, role: "assistant" as const, content: "Pick", created_at: "2026-05-27",
        tool_calls_json: hint },
    ];
    const onWidgetSelect = vi.fn();
    render(<MessageList messages={messages} streamingText="" streamingModuleTag={null} onWidgetSelect={onWidgetSelect} />);
    const card = screen.getByTestId("card-Marketing");
    expect(card).not.toBeDisabled();
  });

  test("widget on a NON-last message is disabled", () => {
    const messages = [
      { id: 1, role: "assistant" as const, content: "Pick", created_at: "2026-05-27",
        tool_calls_json: hint },
      { id: 2, role: "user" as const, content: "I'd like to study Marketing.", created_at: "2026-05-27" },
    ];
    render(<MessageList messages={messages} streamingText="" streamingModuleTag={null} onWidgetSelect={() => {}} />);
    const card = screen.getByTestId("card-Marketing");
    expect(card).toBeDisabled();
  });

  test("widget on last message is disabled while streaming", () => {
    const messages = [
      { id: 1, role: "assistant" as const, content: "Pick", created_at: "2026-05-27",
        tool_calls_json: hint },
    ];
    render(<MessageList messages={messages} streamingText="thinking…" streamingModuleTag={null} onWidgetSelect={() => {}} />);
    const card = screen.getByTestId("card-Marketing");
    expect(card).toBeDisabled();
  });
});
