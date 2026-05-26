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

import type { ListEditorHint } from "./types";

const listEditorHint: ListEditorHint = {
  widget_type: "list_editor",
  field_name: "themes",
  title: "T",
  initial_items: [{ id: "t1", text: "A" }],
};


describe("WidgetRenderer list_editor dispatch", () => {
  test("dispatches list_editor to ListEditorWidget", () => {
    render(<WidgetRenderer hint={listEditorHint} onSelect={() => {}} />);
    expect(screen.getByTestId("list-editor-themes")).toBeTruthy();
  });

  test("forwards disabled prop to ListEditorWidget", () => {
    render(<WidgetRenderer hint={listEditorHint} onSelect={() => {}} disabled />);
    // When disabled, the Confirm button is hidden — sufficient signal that disabled forwarded.
    expect(screen.queryByTestId("list-editor-confirm")).toBeNull();
  });
});
