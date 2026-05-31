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

  test("clicking Other/Specify opens a text input instead of sending", () => {
    const onSelect = vi.fn();
    const hintWithOther: CardGridHint = {
      widget_type: "card_grid",
      field_name: "scope",
      title: "What's the scope?",
      options: [
        { value: "Single University", label: "Single University" },
        { value: "Other", label: "Other / Specify",
          description: "Define a custom scope" },
      ],
    };
    render(<CardGridWidget hint={hintWithOther} onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId("card-Other"));
    // onSelect must NOT have been called yet — input is now visible.
    expect(onSelect).not.toHaveBeenCalled();
    const input = screen.getByTestId("card-other-input") as HTMLInputElement;
    expect(input).toBeTruthy();
  });

  test("multi_select mode: clicking a card does NOT fire onSelect yet", () => {
    const onSelect = vi.fn();
    const multi: CardGridHint = {
      widget_type: "card_grid",
      field_name: "selected_gap_ids",
      title: "Pick gaps",
      multi_select: true,
      options: [
        { value: "1", label: "Gap 1" },
        { value: "2", label: "Gap 2" },
      ],
    };
    render(<CardGridWidget hint={multi} onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId("card-1"));
    expect(onSelect).not.toHaveBeenCalled();
    // A submit button is now visible to commit the picks
    expect(screen.getByTestId("card-multi-submit")).toBeTruthy();
  });

  test("multi_select mode: submit sends comma-joined values and labels", () => {
    const onSelect = vi.fn();
    const multi: CardGridHint = {
      widget_type: "card_grid",
      field_name: "selected_gap_ids",
      title: "Pick gaps",
      multi_select: true,
      options: [
        { value: "1", label: "Gap A" },
        { value: "2", label: "Gap B" },
        { value: "3", label: "Gap C" },
      ],
    };
    render(<CardGridWidget hint={multi} onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId("card-1"));
    fireEvent.click(screen.getByTestId("card-3"));
    fireEvent.click(screen.getByTestId("card-multi-submit"));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(
      "selected_gap_ids",
      "1,3",
      "Gap A, Gap C",
    );
  });

  test("multi_select mode: clicking Other opens text input (not toggle)", () => {
    // W5: multi-select grids (phase3 gaps) include an Other escape hatch.
    // Click must open the typing UI even though we're in multi-select mode,
    // otherwise the user can't propose a custom gap.
    const onSelect = vi.fn();
    const multi: CardGridHint = {
      widget_type: "card_grid",
      field_name: "selected_gap_ids",
      title: "Pick gaps",
      multi_select: true,
      options: [
        { value: "1", label: "Gap A" },
        { value: "Other", label: "Add a different gap" },
      ],
    };
    render(<CardGridWidget hint={multi} onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId("card-Other"));
    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getByTestId("card-other-input")).toBeTruthy();
  });

  test("multi_select mode: submitting Other sends the typed text (not picks)", () => {
    // When the user picks a custom gap, that's its own intent — we don't
    // combine it with whatever cards they may have clicked first.
    const onSelect = vi.fn();
    const multi: CardGridHint = {
      widget_type: "card_grid",
      field_name: "selected_gap_ids",
      title: "Pick gaps",
      multi_select: true,
      options: [
        { value: "1", label: "Gap A" },
        { value: "Other", label: "Add a different gap" },
      ],
    };
    render(<CardGridWidget hint={multi} onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId("card-1"));        // toggled on
    fireEvent.click(screen.getByTestId("card-Other"));    // opens input
    fireEvent.change(screen.getByTestId("card-other-input"),
      { target: { value: "lack of cross-cultural validation" } });
    fireEvent.click(screen.getByTestId("card-other-submit"));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(
      "selected_gap_ids",
      "lack of cross-cultural validation",
      "lack of cross-cultural validation",
    );
  });

  test("multi_select mode: clicking the same card again deselects it", () => {
    const onSelect = vi.fn();
    const multi: CardGridHint = {
      widget_type: "card_grid",
      field_name: "selected_gap_ids",
      title: "Pick gaps",
      multi_select: true,
      options: [
        { value: "1", label: "Gap A" },
        { value: "2", label: "Gap B" },
      ],
    };
    render(<CardGridWidget hint={multi} onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId("card-1"));
    fireEvent.click(screen.getByTestId("card-1"));      // toggle off
    fireEvent.click(screen.getByTestId("card-2"));
    fireEvent.click(screen.getByTestId("card-multi-submit"));
    expect(onSelect).toHaveBeenCalledWith(
      "selected_gap_ids",
      "2",
      "Gap B",
    );
  });

  test("typing in Other input and submitting sends the typed value as the answer", () => {
    const onSelect = vi.fn();
    const hintWithOther: CardGridHint = {
      widget_type: "card_grid",
      field_name: "scope",
      title: "What's the scope?",
      options: [
        { value: "Single University", label: "Single University" },
        { value: "Other", label: "Other / Specify" },
      ],
    };
    render(<CardGridWidget hint={hintWithOther} onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId("card-Other"));
    const input = screen.getByTestId("card-other-input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "Vietnamese university students nationwide" } });
    fireEvent.click(screen.getByTestId("card-other-submit"));
    expect(onSelect).toHaveBeenCalledWith(
      "scope",
      "Vietnamese university students nationwide",
      "Vietnamese university students nationwide",
    );
  });
});
