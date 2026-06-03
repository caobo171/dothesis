import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { FlowChartWidget } from "./FlowChartWidget";
import type { FlowChartHint } from "./types";


const HINT: FlowChartHint = {
  widget_type: "flow_chart",
  field_name: "conceptual_model",
  title: "Conceptual model — constructs, items, and hypothesis paths",
  initial_nodes: [
    { id: "n0", label: "TL",
      questions: ["My supervisor inspires me.",
                  "My supervisor articulates a clear vision."] },
    { id: "n1", label: "EE", questions: ["I feel engaged at work."] },
  ],
  initial_edges: [
    { id: "H1", source: "n0", target: "n1",
      hypothesis: "H1: TL positively affects EE", effect_type: "positive" },
  ],
};


describe("FlowChartWidget", () => {
  test("renders title", () => {
    render(<FlowChartWidget hint={HINT} onSelect={() => {}} />);
    expect(screen.getByText(/Conceptual model/)).toBeTruthy();
  });

  test("data-testid uses field_name", () => {
    render(<FlowChartWidget hint={HINT} onSelect={() => {}} />);
    expect(screen.getByTestId("flow-chart-conceptual_model")).toBeTruthy();
  });

  test("renders each construct's label as an editable input", () => {
    render(<FlowChartWidget hint={HINT} onSelect={() => {}} />);
    expect(screen.getByDisplayValue("TL")).toBeTruthy();
    expect(screen.getByDisplayValue("EE")).toBeTruthy();
  });

  test("renders each construct's questions as editable inputs", () => {
    render(<FlowChartWidget hint={HINT} onSelect={() => {}} />);
    expect(screen.getByDisplayValue("My supervisor inspires me.")).toBeTruthy();
    expect(screen.getByDisplayValue(
      "My supervisor articulates a clear vision.")).toBeTruthy();
    expect(screen.getByDisplayValue("I feel engaged at work.")).toBeTruthy();
  });

  test("renders each path's hypothesis as an editable input", () => {
    render(<FlowChartWidget hint={HINT} onSelect={() => {}} />);
    expect(screen.getByDisplayValue("H1: TL positively affects EE")).toBeTruthy();
  });

  test("Confirm fires onSelect once with the merged conceptual_model JSON + summary", () => {
    const onSelect = vi.fn();
    render(<FlowChartWidget hint={HINT} onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId("flow-chart-confirm"));

    expect(onSelect).toHaveBeenCalledTimes(1);
    const [field, value, label] = onSelect.mock.calls[0];
    expect(field).toBe("conceptual_model");

    const parsed = JSON.parse(value);
    expect(parsed.nodes).toHaveLength(2);
    expect(parsed.nodes[0]).toMatchObject({
      label: "TL",
      questions: ["My supervisor inspires me.",
                  "My supervisor articulates a clear vision."],
    });
    expect(parsed.edges).toHaveLength(1);
    expect(parsed.edges[0]).toMatchObject({
      source: "n0", target: "n1",
      hypothesis: "H1: TL positively affects EE", effect_type: "positive",
    });

    // The human-readable label is what the backend LLM extractor reads
    // from the chat message body. summarizeFlowChart's contract is covered
    // by synthesize.test.ts — here we just sanity-check the hook-up.
    expect(label).toContain("My conceptual model:");
    expect(label).toContain("- TL → EE (H1: TL positively affects EE)");
    expect(label).toContain("Construct TL:");
  });

  test("Add construct appends an empty node row locally without firing onSelect", () => {
    const onSelect = vi.fn();
    render(<FlowChartWidget hint={HINT} onSelect={onSelect} />);

    const before = screen.getAllByTestId(/^flow-node-.+-label$/).length;
    fireEvent.click(screen.getByTestId("flow-chart-add-node"));
    const after = screen.getAllByTestId(/^flow-node-.+-label$/).length;
    expect(after).toBe(before + 1);
    expect(onSelect).not.toHaveBeenCalled();
  });

  test("Add path appends an empty edge row locally without firing onSelect", () => {
    const onSelect = vi.fn();
    render(<FlowChartWidget hint={HINT} onSelect={onSelect} />);

    const before = screen.getAllByTestId(/^flow-edge-.+-hypothesis$/).length;
    fireEvent.click(screen.getByTestId("flow-chart-add-edge"));
    const after = screen.getAllByTestId(/^flow-edge-.+-hypothesis$/).length;
    expect(after).toBe(before + 1);
    expect(onSelect).not.toHaveBeenCalled();
  });

  test("Reset re-seeds nodes + edges from initial hint", () => {
    render(<FlowChartWidget hint={HINT} onSelect={() => {}} />);
    fireEvent.click(screen.getByTestId("flow-chart-add-node"));
    fireEvent.click(screen.getByTestId("flow-chart-add-edge"));
    fireEvent.click(screen.getByTestId("flow-chart-reset"));

    // Back to exactly the initial counts (2 nodes, 1 edge).
    expect(screen.getAllByTestId(/^flow-node-.+-label$/)).toHaveLength(2);
    expect(screen.getAllByTestId(/^flow-edge-.+-hypothesis$/)).toHaveLength(1);
  });

  test("editing a construct label updates the Confirm payload", () => {
    const onSelect = vi.fn();
    render(<FlowChartWidget hint={HINT} onSelect={onSelect} />);

    const tlInput = screen.getByDisplayValue("TL");
    fireEvent.change(tlInput, { target: { value: "Transformational Leadership" } });
    fireEvent.click(screen.getByTestId("flow-chart-confirm"));

    const [, value] = onSelect.mock.calls[0];
    const parsed = JSON.parse(value);
    expect(parsed.nodes[0].label).toBe("Transformational Leadership");
  });

  test("disabled hides Confirm, Reset, Add Node, and Add Path", () => {
    render(<FlowChartWidget hint={HINT} onSelect={() => {}} disabled />);
    expect(screen.queryByTestId("flow-chart-confirm")).toBeNull();
    expect(screen.queryByTestId("flow-chart-reset")).toBeNull();
    expect(screen.queryByTestId("flow-chart-add-node")).toBeNull();
    expect(screen.queryByTestId("flow-chart-add-edge")).toBeNull();
  });
});
