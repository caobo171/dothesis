import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { SourcesRail } from "../SourcesRail";


beforeEach(() => {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ([
      { id: "r1", author: "Smith", year: "2024" },
      { id: "r2", author: "Jones", year: "2023" },
    ]),
  });
});
afterEach(() => vi.restoreAllMocks());


describe("SourcesRail", () => {
  it("renders M2 references", async () => {
    render(<SourcesRail projectId="p1" />);
    await waitFor(() => expect(screen.getByText(/Smith/)).toBeInTheDocument());
    expect(screen.getByText(/Jones/)).toBeInTheDocument();
  });

  it("shows count in header", async () => {
    render(<SourcesRail projectId="p1" />);
    await waitFor(() => expect(screen.getByText(/Sources \(2\)/i)).toBeInTheDocument());
  });

  it("highlights the source matching highlightedId (citation click target)", async () => {
    const { container } = render(<SourcesRail projectId="p1" highlightedId="r2" />);
    await waitFor(() => expect(screen.getByText(/Jones/)).toBeInTheDocument());
    const highlighted = container.querySelector('[aria-current="true"]');
    expect(highlighted?.id).toBe("src-r2");
    // The non-highlighted source is not marked current.
    expect(container.querySelector("#src-r1")?.getAttribute("aria-current")).toBeNull();
  });
});
