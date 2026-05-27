import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SelectionToolbar } from "../SelectionToolbar";


describe("SelectionToolbar", () => {
  it("renders three actions", () => {
    render(<SelectionToolbar onParaphrase={() => {}} onTranslate={() => {}} onCite={() => {}} />);
    expect(screen.getByRole("button", { name: /paraphrase/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /translate/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cite/i })).toBeInTheDocument();
  });

  it("fires onParaphrase when clicked", () => {
    const fn = vi.fn();
    render(<SelectionToolbar onParaphrase={fn} onTranslate={() => {}} onCite={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /paraphrase/i }));
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("fires onTranslate when clicked", () => {
    const fn = vi.fn();
    render(<SelectionToolbar onParaphrase={() => {}} onTranslate={fn} onCite={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /translate/i }));
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("fires onCite when clicked", () => {
    const fn = vi.fn();
    render(<SelectionToolbar onParaphrase={() => {}} onTranslate={() => {}} onCite={fn} />);
    fireEvent.click(screen.getByRole("button", { name: /cite/i }));
    expect(fn).toHaveBeenCalledTimes(1);
  });
});
