import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { CitePopover } from "../CitePopover";


beforeEach(() => {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ([
      { id: "r1", author: "Smith", year: "2024", title: "EU AI Act analysis" },
      { id: "r2", author: "Jones", year: "2023", title: "Algorithmic accountability" },
    ]),
  });
});
afterEach(() => vi.restoreAllMocks());


describe("CitePopover", () => {
  it("loads and lists references from /m5/references", async () => {
    render(<CitePopover projectId="p1" onSelect={() => {}} onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText(/Smith/i)).toBeInTheDocument());
    expect(screen.getByText(/Jones/i)).toBeInTheDocument();
  });

  it("filters by typeahead query", async () => {
    render(<CitePopover projectId="p1" onSelect={() => {}} onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText(/Smith/i)).toBeInTheDocument());
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Jones" } });
    await waitFor(() => {
      expect(screen.queryByText(/Smith/i)).not.toBeInTheDocument();
      expect(screen.getByText(/Jones/i)).toBeInTheDocument();
    });
  });

  it("calls onSelect with the reference id", async () => {
    const onSelect = vi.fn();
    render(<CitePopover projectId="p1" onSelect={onSelect} onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText(/Smith/i)).toBeInTheDocument());
    fireEvent.click(screen.getByText(/Smith/i).closest("button")!);
    expect(onSelect).toHaveBeenCalledWith("r1");
  });

  it("shows empty-pool CTA when references list is empty", async () => {
    (global.fetch as any) = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
    render(<CitePopover projectId="p1" onSelect={() => {}} onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText(/No references/i)).toBeInTheDocument());
  });
});
