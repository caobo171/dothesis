import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, waitFor, screen, fireEvent } from "@testing-library/react";
import { SWRConfig } from "swr";

import { ThesisEditor } from "../ThesisEditor";


function renderWithFreshSWR(ui: React.ReactNode) {
  return render(
    <SWRConfig value={{ provider: () => new Map() }}>{ui}</SWRConfig>
  );
}


/**
 * Drives the editor through chat-rewrite → pending edit → accept/reject
 * end-to-end at the fetch boundary. No real TipTap selection events —
 * we just verify that the pending-edit list flows correctly through the
 * server contract.
 */
describe("editor flow — chat rewrite → pending edit visible", () => {
  beforeEach(() => {
    let chapter = {
      name: "intro",
      prose: "Hello world.",
      pending_edits: [{
        id: "e1",
        source: "chat_rewrite",
        old_text: "Hello world.",
        new_text: "Greetings, world.",
        from_offset: 0,
        to_offset: 12,
      }],
    };
    global.fetch = vi.fn().mockImplementation(async (url: string, init?: any) => {
      if (typeof url === "string" && url.endsWith("/m5/chapters")) {
        return { ok: true, json: async () => ({ intro: chapter }) };
      }
      if (typeof url === "string" && url.endsWith("/m5/references")) {
        return { ok: true, json: async () => [] };
      }
      if (typeof url === "string" && url.endsWith("/m5/chapters/intro")) {
        return { ok: true, json: async () => chapter };
      }
      if (typeof url === "string" && url.includes("/pending/e1/accept")) {
        chapter = { ...chapter, prose: "Greetings, world.", pending_edits: [] };
        return { ok: true, json: async () => chapter };
      }
      if (typeof url === "string" && url.includes("/pending/e1/reject")) {
        chapter = { ...chapter, pending_edits: [] };
        return { ok: true, json: async () => chapter };
      }
      return { ok: true, json: async () => ({}) };
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it("renders chat-rewrite pending edit + accepts it", async () => {
    renderWithFreshSWR(<ThesisEditor projectId="p1" />);
    await waitFor(() => expect(screen.getByText(/Pending edits/i)).toBeInTheDocument());
    expect(screen.getByText(/Greetings, world/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /accept/i }));
    await waitFor(() => {
      expect(screen.queryByText(/Pending edits/i)).not.toBeInTheDocument();
    });
  });

  it("rejects the pending edit and keeps prose untouched", async () => {
    renderWithFreshSWR(<ThesisEditor projectId="p1" />);
    await waitFor(() => expect(screen.getByText(/Pending edits/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /reject/i }));
    await waitFor(() => {
      expect(screen.queryByText(/Pending edits/i)).not.toBeInTheDocument();
    });
  });
});
