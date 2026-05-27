import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { TranslateMenu } from "../TranslateMenu";


describe("TranslateMenu", () => {
  it("renders default language options", () => {
    render(<TranslateMenu defaultLang="vi" onConfirm={() => {}} onClose={() => {}} />);
    expect(screen.getByRole("combobox")).toBeInTheDocument();
    const option = screen.getByRole("option", { name: /vietnamese/i }) as HTMLOptionElement;
    expect(option.selected).toBe(true);
  });

  it("calls onConfirm with selected language", () => {
    const onConfirm = vi.fn();
    render(<TranslateMenu defaultLang="en" onConfirm={onConfirm} onClose={() => {}} />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "fr" } });
    fireEvent.click(screen.getByRole("button", { name: /translate/i }));
    expect(onConfirm).toHaveBeenCalledWith("fr");
  });

  it("cancel closes without confirming", () => {
    const onConfirm = vi.fn();
    const onClose = vi.fn();
    render(<TranslateMenu defaultLang="en" onConfirm={onConfirm} onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });
});
