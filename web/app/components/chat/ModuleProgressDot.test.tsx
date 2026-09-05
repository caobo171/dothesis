import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { ModuleProgressDot } from "./ModuleProgressDot";


// 2026-06-10 — palette assertions updated for the DoThesis.html design badges
// (green/primary/muted/amber) which replaced the old colored dots.
describe("ModuleProgressDot", () => {
  test("renders green badge when done", () => {
    render(<ModuleProgressDot module="M1" status="done" label="Topic Discovery" />);
    expect(screen.getByTestId("dot-M1")).toHaveClass("bg-[var(--ok-fg)]");
  });

  test("renders primary badge when active", () => {
    render(<ModuleProgressDot module="M2" status="active" label="Lit Review" />);
    expect(screen.getByTestId("dot-M2")).toHaveClass("bg-primary-600");
  });

  test("renders muted badge when locked", () => {
    render(<ModuleProgressDot module="M3" status="locked" label="Research Design" />);
    expect(screen.getByTestId("dot-M3")).toHaveClass("bg-ink-200");
  });

  test("renders amber badge when needs_attention", () => {
    render(<ModuleProgressDot module="M4" status="needs_attention" label="Analysis" />);
    expect(screen.getByTestId("dot-M4")).toHaveClass("bg-[var(--pause-bg)]");
  });

  // On a 20-minute unattended run the only question the student has is "is this
  // thing still working?". The page headline spins; the row that is actually
  // running looked exactly as static as the four that are not.
  describe("showing that a step is running", () => {
    test("the active row moves", () => {
      render(<ModuleProgressDot module="M2" status="active" label="Lit Review"
                                detail="Searching sources" />);
      expect(screen.getByTestId("busy-M2")).toBeTruthy();
      expect(screen.getByTestId("dot-M2").className).toMatch(/animate-pulse/);
    });

    test("a step that is not running does not pretend to be", () => {
      const { rerender } = render(
        <ModuleProgressDot module="M2" status="done" label="Lit Review" />);
      expect(screen.queryByTestId("busy-M2")).toBeNull();

      rerender(<ModuleProgressDot module="M2" status="locked" label="Lit Review" />);
      expect(screen.queryByTestId("busy-M2")).toBeNull();

      rerender(<ModuleProgressDot module="M2" status="needs_attention" label="Lit Review" />);
      expect(screen.queryByTestId("busy-M2")).toBeNull();
    });

    test("a finished step says Done, not the last thing it did", () => {
      // Headless never emits `module_complete`, so the detail line from the
      // final beat outlived the work: three green ✓ rows on screen at once, all
      // three reading "tool: commit_slice". A finished step has one thing to
      // report and it is that it finished.
      render(<ModuleProgressDot module="M1" status="done" label="Topic"
                                detail="Saving this step's result" />);
      expect(screen.queryByText("Saving this step's result")).toBeNull();
      expect(screen.getByText(/Done/i)).toBeTruthy();
    });

    test("the status word survives alongside the activity line", () => {
      // A detail line used to REPLACE the status word, so the running row was
      // the only one on screen that never said what state it was in — the
      // locked rows below it said "Locked" and it said "tool: research_scout".
      render(<ModuleProgressDot module="M2" status="active" label="Lit Review"
                                detail="Searching sources" />);
      expect(screen.getByText(/In progress/i)).toBeTruthy();
      expect(screen.getByText("Searching sources")).toBeTruthy();
    });
  });
});
