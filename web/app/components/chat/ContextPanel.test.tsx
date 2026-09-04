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
  test("while the project is loading, does not claim modules are empty", () => {
    // Same class of bug as the chat pane flashing "Start your thesis" over a
    // thread that hasn't arrived: the layout used to pass a null store while
    // /projects/{id} was in flight, and every card said "Topic not set yet".
    render(
      <ContextPanel
        loading
        contextStore={{
          m1_topic: null, m2_literature: null, m3_design: null,
          m4_analysis: null, m5_writing: null,
        }}
        uploads={[]}
      />,
    );
    expect(screen.queryByText(/topic not set yet/i)).toBeNull();
    expect(screen.queryByText(/no literature yet/i)).toBeNull();
    expect(screen.queryByText(/no exports yet/i)).toBeNull();
    expect(screen.getByTestId("context-panel")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByTestId("context-panel-skeleton")).toBeTruthy();
    // Chrome stays — this is the panel loading, not the panel missing.
    expect(screen.getByText("Workspace")).toBeTruthy();
  });

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

  test("a stale module keeps its done status and gets a note, not a warning badge", () => {
    // This asserted the opposite: an upstream mutate flagged M3 and the panel
    // replaced its progress with an amber "Needs review" badge, while the
    // status itself flipped away from done. Both are gone — the student is
    // told their work may be out of date without it being taken off them.
    render(
      <ContextPanel
        contextStore={{
          m1_topic: { confirmed_at: "2026-06-03" },
          m2_literature: { confirmed_at: "2026-06-03" },
          // M3 was confirmed before the upstream M2 edit landed on it.
          m3_design: { confirmed_at: "2026-06-03" },
          m4_analysis: null,
          m5_writing: null,
        }}
        uploads={[]}
        moduleStatus={{ M1: "done", M2: "done", M3: "done", M4: "locked", M5: "locked" }}
        staleModules={["M3"]}
      />,
    );
    // Still done — staleness does not demote it.
    expect(screen.getByTestId("ctx-M3").getAttribute("data-status")).toBe("done");
    expect(screen.getByText(/may be out of date/i)).toBeTruthy();
    // And nothing tells the student to go review it first.
    expect(screen.queryByText(/needs review/i)).toBeNull();
  });

  test("a legacy needs_review row reads as done and stale", () => {
    // Rows written before the migration can still arrive over the wire mid
    // deploy. needs_review always meant "was done, then invalidated", so it
    // must not render as some unknown fourth state.
    render(
      <ContextPanel
        contextStore={{
          m1_topic: { confirmed_at: "2026-06-03" }, m2_literature: null,
          m3_design: { confirmed_at: "2026-06-03" }, m4_analysis: null, m5_writing: null,
        }}
        uploads={[]}
        moduleStatus={{ M1: "done", M2: "locked", M3: "needs_review", M4: "locked", M5: "locked" }}
      />,
    );
    expect(screen.getByTestId("ctx-M3").getAttribute("data-status")).toBe("done");
    expect(screen.getByText(/may be out of date/i)).toBeTruthy();
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
