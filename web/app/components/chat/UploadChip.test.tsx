import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { UploadChip } from "./UploadChip";


describe("UploadChip", () => {
  test("shows filename and page count when extracted", () => {
    render(<UploadChip filename="paper.pdf" pageCount={12} status="ready" onDelete={() => {}} />);
    expect(screen.getByText("paper.pdf")).toBeTruthy();
    expect(screen.getByText(/12 pages/i)).toBeTruthy();
  });

  test("shows 'Extracting' when status=extracting", () => {
    render(<UploadChip filename="paper.pdf" pageCount={null} status="extracting" onDelete={() => {}} />);
    expect(screen.getByText(/extracting/i)).toBeTruthy();
  });

  test("delete button fires callback", () => {
    const onDelete = vi.fn();
    render(<UploadChip filename="x.pdf" pageCount={1} status="ready" onDelete={onDelete} />);
    fireEvent.click(screen.getByRole("button", { name: /delete x\.pdf/i }));
    expect(onDelete).toHaveBeenCalled();
  });
});
