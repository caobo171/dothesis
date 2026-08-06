import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { ReconstructedModules, type ReconstructedModule } from "./ReconstructedModules";

const item = (over: Partial<ReconstructedModule> = {}): ReconstructedModule => ({
  module: "M3",
  candidate: { paradigm: "quantitative", hypotheses: ["H1: A->B"] },
  rationale: "inferred from your analysis",
  ready_to_confirm: false,
  review: ["missing tool"],
  ...over,
});

const regionText = () =>
  screen.getByRole("region", { name: /reconstructed modules/i }).textContent ?? "";

describe("ReconstructedModules", () => {
  test("renders a card per module with its rationale, marked saved", () => {
    render(
      <ReconstructedModules items={[item()]} saved={[{ module: "M3", status: "done" }]} />,
    );
    const text = regionText();
    expect(text).toMatch(/Design/);
    expect(text).toMatch(/inferred from your analysis/);
    expect(text).toMatch(/Saved/);
  });

  test("nothing to confirm or skip — the reconstruction is already committed", () => {
    // The whole point of the change: a student never re-approves a
    // reconstruction of their own work. Any button here is a regression.
    render(
      <ReconstructedModules items={[item()]} saved={[{ module: "M3", status: "done" }]} />,
    );
    expect(screen.queryByRole("button", { name: /confirm/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /skip/i })).toBeNull();
    expect(regionText()).not.toMatch(/not saved yet/i);
  });

  test("a module too thin to earn a done is not drawn as finished", () => {
    render(
      <ReconstructedModules
        items={[item()]}
        saved={[{ module: "M3", status: "in_progress" }]}
      />,
    );
    expect(regionText()).toMatch(/still thin/i);
  });

  test("shows skeleton while reconstructing and nothing when idle+empty", () => {
    const { rerender, container } = render(<ReconstructedModules items={[]} reconstructing />);
    expect(screen.getByText(/reconstructing earlier steps/i)).toBeTruthy();
    rerender(<ReconstructedModules items={[]} />);
    expect(container.textContent).toBe("");
  });

  test("structured fields render as content, never as JSON", () => {
    // research_gaps / hypotheses / conceptual_model used to be dumped into a
    // <pre> as raw JSON — unreadable, and it reads to a student like the
    // product broke. They go through the same renderers the chat context panel
    // uses now, so the card shows the actual gap text.
    render(
      <ReconstructedModules
        items={[
          item({
            module: "M2",
            candidate: {
              research_gaps: [
                { description: "no VN evidence" },
                { description: "no PLS-SEM" },
              ],
            },
            review: [],
          }),
        ]}
        saved={[{ module: "M2", status: "done" }]}
      />,
    );
    const text = regionText();
    expect(text).toMatch(/no VN evidence/);
    expect(text).not.toMatch(/\[object Object\]/);
    expect(text).not.toMatch(/"description":/);
  });

  test("a module with no dedicated renderer still reads as prose, not JSON", () => {
    // M4 has no bespoke body — it falls through to the generic renderer, which
    // must still never print a JSON blob.
    render(
      <ReconstructedModules
        items={[
          item({
            module: "M4",
            candidate: {
              data_type_detected: "survey",
              analysis_outline: { sections: ["measurement", "structural"] },
            },
            review: [],
          }),
        ]}
        saved={[{ module: "M4", status: "done" }]}
      />,
    );
    const text = regionText();
    expect(text).toMatch(/Data type detected/);
    expect(text).toMatch(/survey/);
    expect(text).not.toMatch(/[{}[\]]/);
  });
});
