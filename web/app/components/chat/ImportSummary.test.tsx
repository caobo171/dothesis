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

  test("Continue is disabled while reconstruction is still running", () => {
    // Continuing mid-reconstruction navigates away from steps the student has
    // not reviewed, and the confirm/skip choices live on THIS screen — so an
    // early click silently drops them.
    const onContinue = vi.fn();
    render(
      <ImportSummary imported={["M1"]} focus="M2" onContinue={onContinue} reconstructing />,
    );
    const btn = screen.getByRole("button");
    expect(btn).toBeDisabled();
    expect(btn.getAttribute("aria-busy")).toBe("true");
    expect(btn.textContent).toMatch(/Reconstructing/);
    fireEvent.click(btn);
    expect(onContinue).not.toHaveBeenCalled();
  });

  test("Continue is enabled once reconstruction finishes", () => {
    const onContinue = vi.fn();
    render(
      <ImportSummary imported={["M1"]} focus="M2" onContinue={onContinue} reconstructing={false} />,
    );
    const btn = screen.getByRole("button");
    expect(btn).not.toBeDisabled();
    expect(btn.textContent).toMatch(/Continue to Literature/);
    fireEvent.click(btn);
    expect(onContinue).toHaveBeenCalledTimes(1);
  });

  test("confirming reconstructions is acknowledged, and explains why focus stays", () => {
    // The API commits a confirmed reconstruction as `in_progress` on purpose —
    // "never silently done" — so focus legitimately does NOT advance. Without
    // saying that, the card reads as frozen: you confirm M1/M2/M3 and it still
    // shows "You're at: M1 / Next: Topic".
    render(
      <ImportSummary imported={["M4"]} focus="M1" confirmed={["M1", "M2", "M3"]} />,
    );
    const text = screen.getByRole("region", { name: /import summary/i }).textContent ?? "";
    expect(text).toMatch(/Confirmed:/);
    expect(text).toMatch(/M1 \(Topic\)/);
    expect(text).toMatch(/M3 \(Design\)/);
    expect(text).toMatch(/starting points to review, not finished steps/);
  });

  test("says nothing about confirmations when there are none", () => {
    render(<ImportSummary imported={["M4"]} focus="M1" />);
    const text = screen.getByRole("region", { name: /import summary/i }).textContent ?? "";
    expect(text).not.toMatch(/Confirmed:/);
  });
});
