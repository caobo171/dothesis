import { describe, expect, test } from "vitest";
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
