import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ReExportBar } from "../ReExportBar";


describe("ReExportBar", () => {
  it("shows last-export status", () => {
    const t = new Date(Date.now() - 5 * 60 * 1000);
    render(<ReExportBar lastExportAt={t} editsSinceExport={3} onReExport={() => Promise.resolve()} exporting={false} />);
    expect(screen.getByText(/last export/i)).toBeInTheDocument();
    expect(screen.getByText(/3 edits/i)).toBeInTheDocument();
  });

  it("calls onReExport when button clicked", async () => {
    const onReExport = vi.fn().mockResolvedValue(undefined);
    render(<ReExportBar lastExportAt={null} editsSinceExport={0} onReExport={onReExport} exporting={false} />);
    fireEvent.click(screen.getByRole("button", { name: /re-export/i }));
    expect(onReExport).toHaveBeenCalled();
  });

  it("disables the button while exporting", () => {
    render(<ReExportBar lastExportAt={null} editsSinceExport={0} onReExport={() => Promise.resolve()} exporting={true} />);
    expect(screen.getByRole("button", { name: /exporting/i })).toBeDisabled();
  });

  it("shows error state when error provided", () => {
    render(<ReExportBar lastExportAt={null} editsSinceExport={0} onReExport={() => Promise.resolve()} exporting={false} error={new Error("S3 down")} />);
    expect(screen.getByText(/export failed/i)).toBeInTheDocument();
  });
});
