import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { ModuleProgressDot } from "./ModuleProgressDot";


describe("ModuleProgressDot", () => {
  test("renders green dot when done", () => {
    render(<ModuleProgressDot module="M1" status="done" label="Topic Discovery" />);
    expect(screen.getByTestId("dot-M1")).toHaveClass("bg-green-500");
  });

  test("renders amber dot when active", () => {
    render(<ModuleProgressDot module="M2" status="active" label="Lit Review" />);
    expect(screen.getByTestId("dot-M2")).toHaveClass("bg-amber-500");
  });

  test("renders gray dot when locked", () => {
    render(<ModuleProgressDot module="M3" status="locked" label="Research Design" />);
    expect(screen.getByTestId("dot-M3")).toHaveClass("bg-gray-300");
  });

  test("renders red dot when needs_attention", () => {
    render(<ModuleProgressDot module="M4" status="needs_attention" label="Analysis" />);
    expect(screen.getByTestId("dot-M4")).toHaveClass("bg-red-500");
  });
});
