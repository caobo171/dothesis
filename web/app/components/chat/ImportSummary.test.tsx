import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ImportSummary } from "./ImportSummary";

describe("ImportSummary", () => {
  test("shows imported modules, current focus, and next step", () => {
    render(<ImportSummary imported={["M1", "M3"]} focus="M2" />);
    const region = screen.getByRole("region", { name: /import summary/i });
    const text = region.textContent ?? "";
    // imported modules named
    expect(text).toMatch(/M1/);
    expect(text).toMatch(/M3/);
    // stands at the first NOT-imported module (the focus fix), not M1
    expect(text).toMatch(/You're at:\s*M2/);
    expect(text).toMatch(/Next:\s*Literature/);
  });

  test("surfaces ambiguous files the import couldn't place", () => {
    render(
      <ImportSummary imported={["M1"]} focus="M2" ambiguous={["data.sav"]} />,
    );
    expect(screen.getByText(/data\.sav/)).toBeTruthy();
  });

  test("empty import degrades gracefully", () => {
    render(<ImportSummary imported={[]} focus="M1" />);
    expect(screen.getByText(/nothing to import/i)).toBeTruthy();
  });

  test("continue CTA fires", () => {
    const onContinue = vi.fn();
    render(<ImportSummary imported={["M1"]} focus="M2" onContinue={onContinue} />);
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(onContinue).toHaveBeenCalled();
  });
});
