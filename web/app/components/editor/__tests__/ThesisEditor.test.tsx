import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
// SWRConfig with an isolated provider map gives each test its own cache —
// prevents stale data from the "empty chapters" test bleeding into later tests.
import { SWRConfig } from "swr";
import { ThesisEditor } from "../ThesisEditor";


// Wrap in a fresh SWR cache per render to prevent cross-test cache bleed.
function renderWithFreshCache(ui: React.ReactElement) {
  return render(
    <SWRConfig value={{ provider: () => new Map() }}>
      {ui}
    </SWRConfig>
  );
}


beforeEach(() => {
  global.fetch = vi.fn().mockImplementation(async (url: string) => {
    if (typeof url === "string" && url.endsWith("/m5/chapters")) {
      return { ok: true, json: async () => ({
        intro: { name: "intro", prose: "Intro prose.", pending_edits: [] },
        lit_review: { name: "lit_review", prose: "Lit body.", pending_edits: [] },
      }) };
    }
    if (typeof url === "string" && url.includes("/m5/references")) {
      return { ok: true, json: async () => [] };
    }
    if (typeof url === "string" && url.includes("/m5/chapters/")) {
      return { ok: true, json: async () => ({ name: "intro", prose: "Intro prose.", pending_edits: [] }) };
    }
    return { ok: true, json: async () => ({}) };
  });
});
afterEach(() => vi.restoreAllMocks());


describe("ThesisEditor", () => {
  it("shows the editor skeleton while chapters are loading", () => {
    // Never-resolving fetch keeps SWR in the loading state.
    (global.fetch as any) = vi.fn().mockImplementation(() => new Promise(() => {}));
    renderWithFreshCache(<ThesisEditor projectId="p1" />);
    expect(screen.getByLabelText("Đang tải trình soạn thảo")).toBeInTheDocument();
  });

  it("renders EmptyState when no chapters", async () => {
    (global.fetch as any) = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    renderWithFreshCache(<ThesisEditor projectId="p1" />);
    await waitFor(() => expect(screen.getByText(/M5 hasn't drafted/i)).toBeInTheDocument());
  });

  it("renders OutlineRail with present chapters when populated", async () => {
    renderWithFreshCache(<ThesisEditor projectId="p1" />);
    await waitFor(() => expect(screen.getByText(/Ch 1 — Introduction/)).toBeInTheDocument());
    expect(screen.getByText(/Ch 2 — Literature Review/)).toBeInTheDocument();
  });

  it("stacks every chapter on one page with anchor ids", async () => {
    const { container } = renderWithFreshCache(<ThesisEditor projectId="p1" />);
    // Both chapter bodies render simultaneously (one-page), not one-at-a-time.
    await waitFor(() => expect(screen.getByText(/Intro prose/)).toBeInTheDocument());
    expect(screen.getByText(/Lit body/)).toBeInTheDocument();
    // Each chapter is a scroll target the outline can jump to.
    expect(container.querySelector("#ch-intro")).toBeTruthy();
    expect(container.querySelector("#ch-lit_review")).toBeTruthy();
  });

  it("scrolls to a chapter when its outline entry is clicked", async () => {
    const spy = vi.spyOn(Element.prototype, "scrollIntoView").mockImplementation(() => {});
    renderWithFreshCache(<ThesisEditor projectId="p1" />);
    const entry = await screen.findByText(/Ch 2 — Literature Review/);
    fireEvent.click(entry);
    await waitFor(() => expect(spy).toHaveBeenCalled());
  });

  it("mounts the single shared formatting toolbar once", async () => {
    renderWithFreshCache(<ThesisEditor projectId="p1" />);
    // The toolbar binds to the active chapter editor and must appear exactly
    // once, not once per stacked chapter.
    await waitFor(() => expect(screen.getByRole("toolbar", { name: "Định dạng" })).toBeInTheDocument());
    expect(screen.getAllByRole("toolbar", { name: "Định dạng" })).toHaveLength(1);
  });
});

describe("ThesisEditor legacy chapter keys", () => {
  it("renders no pane for a retired chapter key", async () => {
    // A `discussion` pane would render and be typeable, but PATCH
    // /m5/chapters/discussion 404s (_VALID_CHAPTER_NAMES dropped it), so every
    // autosave retries and parks an error on prose the student can't save.
    // The backfill no longer produces that key; the editor renders canonical
    // chapters only so a stale row in an old project can't resurrect it.
    (global.fetch as any) = vi.fn().mockImplementation(async (url: string) => {
      if (typeof url === "string" && url.endsWith("/m5/chapters")) {
        return { ok: true, json: async () => ({
          intro: { name: "intro", prose: "Intro prose.", pending_edits: [] },
          discussion: { name: "discussion", prose: "Legacy discussion prose.", pending_edits: [] },
        }) };
      }
      return { ok: true, json: async () => [] };
    });
    const { container } = renderWithFreshCache(<ThesisEditor projectId="p1" />);
    await waitFor(() => expect(screen.getByText(/Intro prose/)).toBeInTheDocument());
    expect(container.querySelector("#ch-discussion")).toBeNull();
    expect(screen.queryByText(/Legacy discussion prose/)).not.toBeInTheDocument();
  });
});
