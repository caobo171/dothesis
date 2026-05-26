import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ListEditorWidget } from "./ListEditorWidget";
import type { ListEditorHint } from "./types";


const flatHint: ListEditorHint = {
  widget_type: "list_editor",
  field_name: "purposive_criteria",
  title: "Sampling criteria",
  initial_items: [
    { id: "c0", text: "At SME" },
    { id: "c1", text: "6mo+ tenure" },
  ],
};

const nestedHint: ListEditorHint = {
  widget_type: "list_editor",
  field_name: "themes",
  title: "Themes",
  initial_items: [
    { id: "t1", text: "Theme 1", sub_items: [{ id: "s1", text: "Sub A" }] },
    { id: "t2", text: "Theme 2", sub_items: [] },
  ],
  allow_nested: true,
};


describe("ListEditorWidget", () => {
  test("renders title and initial items", () => {
    render(<ListEditorWidget hint={flatHint} onSelect={() => {}} />);
    expect(screen.getByText("Sampling criteria")).toBeTruthy();
    expect(screen.getByDisplayValue("At SME")).toBeTruthy();
    expect(screen.getByDisplayValue("6mo+ tenure")).toBeTruthy();
  });

  test("data-testid uses field_name", () => {
    render(<ListEditorWidget hint={flatHint} onSelect={() => {}} />);
    expect(screen.getByTestId("list-editor-purposive_criteria")).toBeTruthy();
  });

  test("nested hint renders sub_items", () => {
    render(<ListEditorWidget hint={nestedHint} onSelect={() => {}} />);
    expect(screen.getByDisplayValue("Theme 1")).toBeTruthy();
    expect(screen.getByDisplayValue("Sub A")).toBeTruthy();
  });

  test("Add button appends a new item locally without firing onSelect", () => {
    const onSelect = vi.fn();
    render(<ListEditorWidget hint={flatHint} onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId("list-editor-add"));
    expect(onSelect).not.toHaveBeenCalled();
  });

  test("Remove button removes the item locally without firing onSelect", () => {
    const onSelect = vi.fn();
    render(<ListEditorWidget hint={flatHint} onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId("list-item-c0-remove"));
    expect(screen.queryByDisplayValue("At SME")).toBeNull();
    expect(onSelect).not.toHaveBeenCalled();
  });

  test("Confirm fires onSelect with structured JSON value + bulleted label", () => {
    const onSelect = vi.fn();
    render(<ListEditorWidget hint={flatHint} onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId("list-editor-confirm"));
    expect(onSelect).toHaveBeenCalledTimes(1);
    const [field, value, label] = onSelect.mock.calls[0];
    expect(field).toBe("purposive_criteria");
    const parsed = JSON.parse(value);
    expect(parsed).toHaveLength(2);
    expect(parsed[0].text).toBe("At SME");
    expect(label).toContain("My sampling criteria:");
    expect(label).toContain("- At SME");
  });

  test("Reset re-seeds from initial_items", () => {
    render(<ListEditorWidget hint={flatHint} onSelect={() => {}} />);
    fireEvent.click(screen.getByTestId("list-item-c0-remove"));
    expect(screen.queryByDisplayValue("At SME")).toBeNull();
    fireEvent.click(screen.getByTestId("list-editor-reset"));
    expect(screen.getByDisplayValue("At SME")).toBeTruthy();
  });

  test("disabled prop hides Confirm and Reset buttons", () => {
    render(<ListEditorWidget hint={flatHint} onSelect={() => {}} disabled />);
    expect(screen.queryByTestId("list-editor-confirm")).toBeNull();
    expect(screen.queryByTestId("list-editor-reset")).toBeNull();
  });

  test("disabled prop locks editing — no Add and no Remove visible", () => {
    render(<ListEditorWidget hint={flatHint} onSelect={() => {}} disabled />);
    expect(screen.queryByTestId("list-editor-add")).toBeNull();
    expect(screen.queryByTestId("list-item-c0-remove")).toBeNull();
  });
});
