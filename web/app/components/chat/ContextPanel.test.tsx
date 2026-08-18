import { describe, expect, test } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ContextPanel, formatExportScope } from "./ContextPanel";


const _baseCtx = {
  m1_topic: { research_title: "X", confirmed_at: "2026-05-26" },
  m2_literature: null,
  m3_design: null,
  m4_analysis: null,
  m5_writing: null,
};

describe("export scope labels", () => {
  test("turns chapter protocol scopes into student-facing names", () => {
    expect(formatExportScope("chapter:intro|lit_review|methodology")).toBe("Chương 1–3");
    expect(formatExportScope("chapter:methodology")).toBe("Chương 3");
    expect(formatExportScope("full")).toBe("Toàn bộ luận văn");
  });
});


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
    expect(screen.getByTestId("dot-M1")).toHaveClass("bg-[var(--ok-fg)]");
    expect(screen.getByTestId("dot-M2")).toHaveClass("bg-ink-200");
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

  test("module_status needs_review renders amber ⚠ badge (brief §1.5)", () => {
    // Brief §1.5: when an upstream mutate flags M3 as needs_review, the
    // panel must surface a review badge regardless of whether M3 had been
    // confirmed before (which would otherwise show green). Reuses the
    // existing `needs_attention` ModuleStatus so no theming work is needed.
    render(
      <ContextPanel
        contextStore={{
          m1_topic: { confirmed_at: "2026-06-03" },
          m2_literature: { confirmed_at: "2026-06-03" },
          // M3 was confirmed before the upstream M2 mutate hit it —
          // confirmed_at is still set, but module_status now flags review.
          m3_design: { confirmed_at: "2026-06-03" },
          m4_analysis: null,
          m5_writing: null,
        }}
        uploads={[]}
        moduleStatus={{ M1: "done", M2: "done", M3: "needs_review", M4: "locked", M5: "locked" }}
      />,
    );
    expect(screen.getByTestId("dot-M3")).toHaveClass("bg-[var(--pause-bg)]");
    // Sanity: confirmed-and-not-flagged stays green.
    expect(screen.getByTestId("dot-M1")).toHaveClass("bg-[var(--ok-fg)]");
  });

  test("missing module_status falls back to legacy context-store derivation", () => {
    // Old projects (no turn yet → module_status is {}) must keep rendering
    // sensibly — no red dots for empty modules, just the legacy locked/done/active.
    render(<ContextPanel contextStore={_baseCtx} uploads={[]} />);
    expect(screen.getByTestId("dot-M1")).toHaveClass("bg-[var(--ok-fg)]");  // confirmed
    expect(screen.getByTestId("dot-M2")).toHaveClass("bg-ink-200");  // locked
  });

  test("uploads list shows filenames", () => {
    render(<ContextPanel contextStore={_baseCtx} uploads={[
      { id: "u1", filename: "paper.pdf", size_bytes: 1234, mime_type: "application/pdf", page_count: 12, uploaded_at: "2026-05-27" },
    ]} />);
    expect(screen.getByText("paper.pdf")).toBeTruthy();
  });
});
