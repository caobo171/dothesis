import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { WidgetRenderer } from "./WidgetRenderer";
import type { CardGridHint } from "./types";


const cardGridHint: CardGridHint = {
  widget_type: "card_grid",
  field_name: "field",
  title: "Pick",
  options: [{ value: "x", label: "X" }],
};


describe("WidgetRenderer", () => {
  test("dispatches card_grid to CardGridWidget", () => {
    render(<WidgetRenderer hint={cardGridHint} onSelect={() => {}} />);
    expect(screen.getByTestId("card-grid-field")).toBeTruthy();
  });

  test("returns null for unknown widget_type (forward-compat)", () => {
    const { container } = render(
      <WidgetRenderer
        hint={{ widget_type: "future_widget" } as never}
        onSelect={() => {}}
      />,
    );
    expect(container.innerHTML).toBe("");
  });

  test("forwards disabled prop", () => {
    render(<WidgetRenderer hint={cardGridHint} onSelect={() => {}} disabled />);
    const btn = screen.getByTestId("card-x");
    expect(btn).toBeDisabled();
  });
});
