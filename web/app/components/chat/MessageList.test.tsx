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

  test("renders ProgressBubble when in-flight with progress but no tokens yet", () => {
    // P4: M2 phase2's 30-60s scout used to show only the typing dot. With
    // engine progress streamed, the bubble shows the live line(s).
    render(
      <MessageList
        messages={[]}
        streamingText=""
        streamingModuleTag="M2"
        inflight={true}
        streamingProgress={[
          { stage: "scout.start", message: "Searching for citations..." },
          { stage: "scout.api_chain", message: "API chain: gemini → crossref" },
        ]}
      />
    );
    expect(screen.getByTestId("progress-bubble")).toBeTruthy();
    // Latest line is the headline; previous one is faded but present.
    expect(screen.getByText("API chain: gemini → crossref")).toBeTruthy();
    expect(screen.getByText("Searching for citations...")).toBeTruthy();
    // No bare thinking-bubble when progress is available.
    expect(screen.queryByTestId("thinking-bubble")).toBeNull();
  });

  test("falls back to ThinkingBubble when in-flight but no progress yet", () => {
    render(
      <MessageList
        messages={[]}
        streamingText=""
        streamingModuleTag={null}
        inflight={true}
        streamingProgress={[]}
      />
    );
    expect(screen.getByTestId("thinking-bubble")).toBeTruthy();
    expect(screen.queryByTestId("progress-bubble")).toBeNull();
  });

  test("renders ErrorBubble when streamingError is set", () => {
    // P6: backend SSE `type: error` must surface visibly — the M2 msgpack
    // crash showed silent failure is the worst possible UX.
    render(
      <MessageList
        messages={[]}
        streamingText=""
        streamingModuleTag={null}
        inflight={false}
        streamingError="TypeError: Type is not msgpack serializable: function"
      />
    );
    expect(screen.getByTestId("error-bubble")).toBeTruthy();
    expect(screen.getByText(/msgpack/)).toBeTruthy();
    expect(screen.getByText("Something went wrong")).toBeTruthy();
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
