import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SelectionToolbar } from "../SelectionToolbar";

const noop = () => {};
const handlers = () => ({
  onParaphrase: noop, onTranslate: noop, onCite: noop,
  onProofread: noop, onImprove: noop, onHumanize: noop,
  onExpand: noop, onShorten: noop,
});


describe("SelectionToolbar", () => {
  it("shows the bar: Ask AI + Translate + Cite, with rewrites hidden until opened", () => {
    render(<SelectionToolbar {...handlers()} />);
    expect(screen.getByRole("button", { name: /ask ai/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /translate/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cite/i })).toBeInTheDocument();
    // Rewrite actions live in the dropdown — not rendered until it opens.
    expect(screen.queryByRole("menuitem", { name: /paraphrase/i })).toBeNull();
  });

  it("opens the Ask AI dropdown to reveal the rewrite actions", () => {
    render(<SelectionToolbar {...handlers()} />);
    fireEvent.click(screen.getByRole("button", { name: /ask ai/i }));
    for (const name of [/paraphrase/i, /improve/i, /proofread/i, /humanize/i, /expand/i, /shorten/i]) {
      expect(screen.getByRole("menuitem", { name })).toBeInTheDocument();
    }
  });

  it.each([
    ["onParaphrase", /paraphrase/i],
    ["onImprove", /improve/i],
    ["onProofread", /proofread/i],
    ["onHumanize", /humanize/i],
    ["onExpand", /expand/i],
    ["onShorten", /shorten/i],
  ] as const)("fires %s from the dropdown", (prop, name) => {
    const fn = vi.fn();
    render(<SelectionToolbar {...handlers()} {...{ [prop]: fn }} />);
    fireEvent.click(screen.getByRole("button", { name: /ask ai/i }));
    fireEvent.click(screen.getByRole("menuitem", { name }));
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["onTranslate", /translate/i],
    ["onCite", /cite/i],
  ] as const)("fires %s directly from the bar", (prop, name) => {
    const fn = vi.fn();
    render(<SelectionToolbar {...handlers()} {...{ [prop]: fn }} />);
    fireEvent.click(screen.getByRole("button", { name }));
    expect(fn).toHaveBeenCalledTimes(1);
  });
});
