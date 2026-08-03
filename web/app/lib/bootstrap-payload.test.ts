import { describe, expect, test } from "vitest";

import { formatAnalyzeMessage } from "./bootstrap-payload";

describe("formatAnalyzeMessage", () => {
  test("defaults to the assessment turn", () => {
    const msg = formatAnalyzeMessage("", true);
    expect(msg.startsWith("/bootstrap")).toBe(true);
    expect(msg).toMatch(/which thesis modules/);
    expect(msg).not.toMatch(/humanize/i);
  });

  test("humanize loads the skill directly instead of the bootstrap assessment", () => {
    // "/bootstrap" triggers dothesis-bootstrap, which classifies uploads into
    // M1-M5 and reports where the thesis stands. A student who came to fix
    // their prose did not ask for that, and humanize_prose reads no module
    // state, so the turn loads the humanize skill directly.
    const msg = formatAnalyzeMessage("", true, "humanize");
    expect(msg.startsWith("/bootstrap")).toBe(false);
    expect(msg).toMatch(/Use the `dothesis-humanize` skill/);
    expect(msg).toMatch(/Don't set up thesis modules or assess my research design/);
  });

  test("humanize asks for the anchor before rewriting", () => {
    // dothesis-humanize refuses to run unanchored and the shipped anchor
    // library is empty by design, so a humanize turn that doesn't ask for the
    // student's own words dead-ends on `no_anchor` with nothing on screen
    // explaining why. This instruction is what prevents that.
    const msg = formatAnalyzeMessage("", true, "humanize");
    expect(msg).toMatch(/humanize pass/);
    expect(msg).toMatch(/150 words I wrote myself/);
    expect(msg).toMatch(/BEFORE rewriting/);
    // Frozen content is the whole safety property of the rewrite.
    expect(msg).toMatch(/Keep every number, statistic and citation/);
  });

  test("humanize without files asks for the passage instead of reading uploads", () => {
    const msg = formatAnalyzeMessage("", false, "humanize");
    expect(msg).toMatch(/paste the passage/);
    expect(msg).not.toMatch(/uploaded/);
  });

  test("the student's own note is carried through in both kinds", () => {
    expect(formatAnalyzeMessage("chương 4 thôi", true, "humanize"))
      .toMatch(/My own notes:\nchương 4 thôi/);
    expect(formatAnalyzeMessage("chương 4 thôi", true))
      .toMatch(/My own notes:\nchương 4 thôi/);
  });
});
