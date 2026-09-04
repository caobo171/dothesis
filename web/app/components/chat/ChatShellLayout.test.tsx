import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChatShellLayout } from "./ChatShellLayout";


describe("ChatShellLayout", () => {
  test("renders all 3 panes", () => {
    render(
      <ChatShellLayout
        leftPane={<div>LEFT</div>}
        rightPane={<div>RIGHT</div>}
      >
        <div>CENTER</div>
      </ChatShellLayout>,
    );
    expect(screen.getByText("LEFT")).toBeTruthy();
    expect(screen.getByText("CENTER")).toBeTruthy();
    expect(screen.getByText("RIGHT")).toBeTruthy();
  });

  test("drops the right pane and its resize handle when rightPane is null (editor mode)", () => {
    render(
      <ChatShellLayout leftPane={<div>LEFT</div>} rightPane={null}>
        <div>CENTER</div>
      </ChatShellLayout>,
    );
    expect(screen.getByText("LEFT")).toBeTruthy();
    expect(screen.getByText("CENTER")).toBeTruthy();
    expect(screen.queryByRole("separator", { name: "Resize context panel" })).toBeNull();
  });
});
