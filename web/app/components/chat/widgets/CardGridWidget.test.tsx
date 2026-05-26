// web/app/components/chat/widgets/CardGridWidget.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { CardGridWidget } from "./CardGridWidget";
import type { CardGridHint } from "./types";


const hint: CardGridHint = {
  widget_type: "card_grid",
  field_name: "field",
  title: "Pick a field",
  options: [
    { value: "Marketing", label: "Marketing", description: "Brand & ads" },
    { value: "Economics", label: "Economics" },
  ],
};


describe("CardGridWidget", () => {
  test("renders title and option cards", () => {
    render(<CardGridWidget hint={hint} onSelect={() => {}} />);
    expect(screen.getByText("Pick a field")).toBeTruthy();
    expect(screen.getByText("Marketing")).toBeTruthy();
    expect(screen.getByText("Brand & ads")).toBeTruthy();
    expect(screen.getByText("Economics")).toBeTruthy();
  });

  test("clicking an option fires onSelect with field_name/value/label", () => {
    const onSelect = vi.fn();
    render(<CardGridWidget hint={hint} onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId("card-Marketing"));
    expect(onSelect).toHaveBeenCalledWith("field", "Marketing", "Marketing");
  });

  test("disabled prevents click", () => {
    const onSelect = vi.fn();
    render(<CardGridWidget hint={hint} onSelect={onSelect} disabled />);
    fireEvent.click(screen.getByTestId("card-Marketing"));
    expect(onSelect).not.toHaveBeenCalled();
  });

  test("data-testid uses field_name", () => {
    render(<CardGridWidget hint={hint} onSelect={() => {}} />);
    expect(screen.getByTestId("card-grid-field")).toBeTruthy();
  });
});
