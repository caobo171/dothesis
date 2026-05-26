import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
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
