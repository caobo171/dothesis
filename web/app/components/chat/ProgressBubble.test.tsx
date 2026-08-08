import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";

import { ProgressBubble, dedupeProgress } from "./ProgressBubble";

const P = (message: string) => ({ stage: "s", message });

describe("dedupeProgress", () => {
  test("collapses a run of the same message into one line with a count", () => {
    // The engine narrates per CALL, not per distinct activity, so a turn that
    // read two skills and looked two things up printed four lines saying two
    // things — and the repeats pushed the genuinely different earlier steps
    // out of the visible window.
    const out = dedupeProgress([
      P("Looking something up..."),
      P("Reading the guide for this step..."),
      P("Looking something up..."),
      P("Looking something up..."),
    ]);
    expect(out.map(o => [o.message, o.times])).toEqual([
      ["Looking something up...", 1],
      ["Reading the guide for this step...", 1],
      ["Looking something up...", 2],
    ]);
  });

  test("only collapses ADJACENT repeats — a step that comes back is real motion", () => {
    const out = dedupeProgress([P("a"), P("b"), P("a")]);
    expect(out).toHaveLength(3);
  });

  test("survives an empty stream", () => {
    expect(dedupeProgress([])).toEqual([]);
  });
});

describe("ProgressBubble", () => {
  test("headlines the newest step", () => {
    render(<ProgressBubble progress={[P("Searching Crossref..."), P("Reading the guide...")]} />);
    // Once in the headline, once in the screen-reader line.
    expect(screen.getAllByText("Reading the guide...").length).toBeGreaterThan(0);
  });

  test("the repeat count reaches the screen, not just the dedupe", () => {
    render(<ProgressBubble progress={[P("dup"), P("dup"), P("newest")]} />);
    expect(screen.getByText("×2")).toBeTruthy();
  });

  test("a single step shows no trail to read", () => {
    render(<ProgressBubble progress={[P("only one")]} />);
    expect(screen.queryByTestId("progress-line-prev")).toBeNull();
  });
});
