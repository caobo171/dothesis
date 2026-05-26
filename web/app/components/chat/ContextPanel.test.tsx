import { describe, expect, test } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ContextPanel } from "./ContextPanel";


const _baseCtx = {
  m1_topic: { research_title: "X", confirmed_at: "2026-05-26" },
  m2_literature: null,
  m3_design: null,
  m4_analysis: null,
  m5_writing: null,
};


describe("ContextPanel", () => {
  test("renders all 5 module dots", () => {
    render(<ContextPanel contextStore={_baseCtx} uploads={[]} />);
    expect(screen.getByTestId("dot-M1")).toBeTruthy();
    expect(screen.getByTestId("dot-M2")).toBeTruthy();
    expect(screen.getByTestId("dot-M3")).toBeTruthy();
    expect(screen.getByTestId("dot-M4")).toBeTruthy();
    expect(screen.getByTestId("dot-M5")).toBeTruthy();
  });

  test("M1 confirmed → done; M2 locked", () => {
    render(<ContextPanel contextStore={_baseCtx} uploads={[]} />);
    expect(screen.getByTestId("dot-M1")).toHaveClass("bg-green-500");
    expect(screen.getByTestId("dot-M2")).toHaveClass("bg-gray-300");
  });

  test("clicking a confirmed module shows its content", () => {
    render(<ContextPanel contextStore={_baseCtx} uploads={[]} />);
    // Open the M1 accordion in the module viewer section
    const viewers = screen.getAllByRole("button");
    // Find the one with "M1 · Topic" prefix
    const m1Viewer = viewers.find(b => /M1.*Topic/i.test(b.textContent ?? ""));
    expect(m1Viewer).toBeTruthy();
    fireEvent.click(m1Viewer!);
    expect(screen.getByText(/research_title/i)).toBeTruthy();
  });

  test("uploads list shows filenames", () => {
    render(<ContextPanel contextStore={_baseCtx} uploads={[
      { id: "u1", filename: "paper.pdf", size_bytes: 1234, mime_type: "application/pdf", page_count: 12, uploaded_at: "2026-05-27" },
    ]} />);
    expect(screen.getByText("paper.pdf")).toBeTruthy();
  });
});
