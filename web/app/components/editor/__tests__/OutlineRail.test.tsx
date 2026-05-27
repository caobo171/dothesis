import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { OutlineRail } from "../OutlineRail";


describe("OutlineRail", () => {
  it("renders all present chapters in canonical order", () => {
    render(
      <OutlineRail
        present={["intro", "lit_review", "methodology", "results", "discussion", "conclusion"]}
        active="methodology"
        onSelect={() => {}}
      />
    );
    const items = screen.getAllByRole("button");
    expect(items.map(b => b.textContent)).toEqual([
      "Ch 1 — Introduction",
      "Ch 2 — Literature Review",
      "Ch 3 — Methodology",
      "Ch 4 — Results",
      "Ch 5 — Discussion",
      "Ch 6 — Conclusion",
    ]);
  });

  it("highlights the active chapter", () => {
    render(<OutlineRail present={["intro", "lit_review"]} active="lit_review" onSelect={() => {}} />);
    const active = screen.getByRole("button", { name: /lit/i });
    expect(active.className).toMatch(/bg-/);
    expect(active).toHaveAttribute("aria-current", "true");
  });

  it("calls onSelect with the chapter name on click", () => {
    const onSelect = vi.fn();
    render(<OutlineRail present={["intro", "lit_review"]} active="intro" onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: /literature/i }));
    expect(onSelect).toHaveBeenCalledWith("lit_review");
  });

  it("dims chapters not in `present`", () => {
    render(<OutlineRail present={["intro"]} active="intro" onSelect={() => {}} />);
    const drafting = screen.getByRole("button", { name: /literature/i });
    expect(drafting).toBeDisabled();
  });
});
