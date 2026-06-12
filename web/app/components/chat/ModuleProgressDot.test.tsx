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
});
