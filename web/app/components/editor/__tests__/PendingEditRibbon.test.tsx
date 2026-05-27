import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PendingEditRibbon } from "../PendingEditRibbon";


describe("PendingEditRibbon", () => {
  it("shows source label", () => {
    render(<PendingEditRibbon edit={{
      id: "e1", source: "paraphrase", oldText: "x", newText: "y", from_offset: 0, to_offset: 1,
    }} onAccept={() => {}} onReject={() => {}} stale={false} />);
    expect(screen.getByText(/paraphrase/i)).toBeInTheDocument();
  });

  it("calls onAccept when ✓ clicked", () => {
    const onAccept = vi.fn();
    render(<PendingEditRibbon edit={{ id: "e1", source: "paraphrase", oldText: "", newText: "", from_offset: 0, to_offset: 0 }}
                              onAccept={onAccept} onReject={() => {}} stale={false} />);
    fireEvent.click(screen.getByRole("button", { name: /accept/i }));
    expect(onAccept).toHaveBeenCalledWith("e1");
  });

  it("calls onReject when ✗ clicked", () => {
    const onReject = vi.fn();
    render(<PendingEditRibbon edit={{ id: "e1", source: "paraphrase", oldText: "", newText: "", from_offset: 0, to_offset: 0 }}
                              onAccept={() => {}} onReject={onReject} stale={false} />);
    fireEvent.click(screen.getByRole("button", { name: /reject/i }));
    expect(onReject).toHaveBeenCalledWith("e1");
  });

  it("renders stale state with Discard CTA", () => {
    const onReject = vi.fn();
    render(<PendingEditRibbon edit={{ id: "e1", source: "paraphrase", oldText: "", newText: "", from_offset: 0, to_offset: 0 }}
                              onAccept={() => {}} onReject={onReject} stale={true} />);
    expect(screen.getByText(/stale/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /discard/i }));
    expect(onReject).toHaveBeenCalledWith("e1");
  });
});
