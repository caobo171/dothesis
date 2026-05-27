import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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
});
