import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ReconstructedModules, type ReconstructedModule } from "./ReconstructedModules";

const item = (over: Partial<ReconstructedModule> = {}): ReconstructedModule => ({
  module: "M3",
  candidate: { paradigm: "quantitative", hypotheses: ["H1: A->B"] },
  rationale: "inferred from your analysis",
  ready_to_confirm: false,
  review: ["missing tool"],
  ...over,
});

describe("ReconstructedModules", () => {
  test("renders a card per module with rationale and the not-saved badge", () => {
    render(<ReconstructedModules items={[item()]} onConfirm={vi.fn()} />);
    const region = screen.getByRole("region", { name: /reconstructed modules/i });
    const text = region.textContent ?? "";
    expect(text).toMatch(/Design/);
    expect(text).toMatch(/inferred from your analysis/);
    expect(text).toMatch(/not saved yet/i);
  });

  test("confirm sends the EDITED candidate", async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    render(<ReconstructedModules items={[item()]} onConfirm={onConfirm} />);
    // Edit the string field.
    const input = screen.getByDisplayValue("quantitative") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "qualitative" } });
    fireEvent.click(screen.getByRole("button", { name: /confirm/i }));
    await waitFor(() => expect(onConfirm).toHaveBeenCalled());
    const [module, edited] = onConfirm.mock.calls[0];
    expect(module).toBe("M3");
    expect(edited.paradigm).toBe("qualitative");
    // Array field is preserved.
    expect(edited.hypotheses).toEqual(["H1: A->B"]);
  });

  test("skip removes the card without confirming", () => {
    const onConfirm = vi.fn();
    const onSkip = vi.fn();
    render(<ReconstructedModules items={[item()]} onConfirm={onConfirm} onSkip={onSkip} />);
    fireEvent.click(screen.getByRole("button", { name: /skip/i }));
    expect(onSkip).toHaveBeenCalledWith("M3");
    expect(onConfirm).not.toHaveBeenCalled();
  });

  test("shows skeleton while reconstructing and nothing when idle+empty", () => {
    const { rerender, container } = render(
      <ReconstructedModules items={[]} reconstructing onConfirm={vi.fn()} />,
    );
    expect(screen.getByText(/reconstructing earlier steps/i)).toBeTruthy();
    rerender(<ReconstructedModules items={[]} onConfirm={vi.fn()} />);
    expect(container.textContent).toBe("");
  });

  test("an array of OBJECTS is never rendered as [object Object]", () => {
    // research_gaps / hypotheses / constructs / purposive_criteria arrive as
    // arrays of objects. They used to hit the line-editable textarea branch,
    // where String({...}) printed "[object Object]" per row — and worse, the
    // onChange would split("\n") those rows back into plain strings, silently
    // destroying the reconstruction the moment anyone typed in the field.
    render(
      <ReconstructedModules
        items={[
          {
            module: "M2",
            fields: {
              research_gaps: [
                { id: "G1", text: "no VN evidence" },
                { id: "G2", text: "no PLS-SEM" },
              ],
            },
          } as any,
        ]}
        onConfirm={() => {}}
      />,
    );
    const region = screen.getByRole("region", { name: /reconstructed modules/i });
    const text = region.textContent ?? "";
    expect(text).not.toMatch(/\[object Object\]/);
    // rendered as the read-only structured preview instead
    expect(text).toMatch(/refine in chat/);
    expect(text).toMatch(/no VN evidence/);
  });

  test("an empty / null field says so instead of printing null", () => {
    render(
      <ReconstructedModules
        items={[{ module: "M3", fields: { themes: null } } as any]}
        onConfirm={() => {}}
      />,
    );
    const text = screen.getByRole("region", { name: /reconstructed modules/i }).textContent ?? "";
    expect(text).toMatch(/Not reconstructed/);
    expect(text).not.toMatch(/^null$/m);
  });
});
