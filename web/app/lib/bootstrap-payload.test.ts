import { beforeEach, describe, expect, test } from "vitest";

import {
  formatAnalyzeMessage,
  readAnalyzeIntent,
  stashAnalyzeIntent,
} from "./bootstrap-payload";

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

describe("formatAnalyzeMessage — preseeded (server-side import already ran)", () => {
  test("sends the student's sentence, not a re-classification", () => {
    // mid-journey-import + reconstruct already read these files, classified
    // them into M1-M5 and committed the state, deterministically. Re-running
    // /bootstrap would pay an LLM to re-derive what the import card is already
    // showing — and could derive it differently.
    const msg = formatAnalyzeMessage("write chapter 5 in English", true, "assess", true);
    expect(msg).toBe("write chapter 5 in English");
    expect(msg.startsWith("/bootstrap")).toBe(false);
    expect(msg).not.toMatch(/which thesis modules/);
  });

  test("humanize is unaffected — it never seeded modules to begin with", () => {
    const msg = formatAnalyzeMessage("", true, "humanize", true);
    expect(msg).toMatch(/Use the `dothesis-humanize` skill/);
  });

  test("without preseeded the assessment turn is unchanged", () => {
    const msg = formatAnalyzeMessage("write chapter 5 in English", true);
    expect(msg.startsWith("/bootstrap")).toBe(true);
  });
});

describe("stashAnalyzeIntent", () => {
  const KEY = "dothesis_analyze_v1:p1";
  beforeEach(() => window.sessionStorage.clear());

  test("keeps the note typed alongside an upload", () => {
    // The /new import branch used to return before stashing, so attaching a
    // file silently discarded whatever the student had written next to it and
    // they landed in an empty thread with their request never asked.
    stashAnalyzeIntent("p1", {
      kind: "assess", note: "viết chương 5 bằng tiếng Anh",
      attachments: [], preseeded: true,
    });
    const got = readAnalyzeIntent("p1");
    expect(got?.note).toBe("viết chương 5 bằng tiếng Anh");
    expect(got?.preseeded).toBe(true);
  });

  test("writes nothing when preseeded and the student typed nothing", () => {
    // The import already reported where they stand on the activation card.
    // A turn here would bill them to be told what is on the screen behind it.
    stashAnalyzeIntent("p1", {
      kind: "assess", note: "   ",
      attachments: [{ upload_id: "u1", filename: "t.docx", size_bytes: 1 }],
      preseeded: true,
    });
    expect(window.sessionStorage.getItem(KEY)).toBeNull();
  });

  test("a non-preseeded upload with no note still fires the assessment", () => {
    stashAnalyzeIntent("p1", {
      kind: "assess", note: "",
      attachments: [{ upload_id: "u1", filename: "t.docx", size_bytes: 1 }],
    });
    expect(readAnalyzeIntent("p1")?.attachments).toHaveLength(1);
  });


// --- Auto Thesis entry from /new -------------------------------------------
// Picking "Auto Thesis" on the start screen is not a variation on the first
// chat turn — it means there should be NO first chat turn. The run seeds M1
// itself (_seed_brief), so firing /bootstrap alongside it would have two
// things writing the same slice at once.

describe("autoThesis intent", () => {
  test("rides on the stash so the chat surface can act on it", () => {
    stashAnalyzeIntent("p-auto", {
      note: "Leadership in Vietnamese SMEs", attachments: [], autoThesis: true,
    });
    expect(readAnalyzeIntent("p-auto")).toMatchObject({
      note: "Leadership in Vietnamese SMEs", autoThesis: true,
    });
  });

  test("is absent on a normal guided start", () => {
    stashAnalyzeIntent("p-guided", { note: "help me", attachments: [] });
    expect(readAnalyzeIntent("p-guided")?.autoThesis).toBeUndefined();
  });

  test("still needs something to run on — a blank start writes no stash", () => {
    stashAnalyzeIntent("p-blank", { note: "  ", attachments: [], autoThesis: true });
    expect(readAnalyzeIntent("p-blank")).toBeNull();
  });
});

  test("survives the preseeded blank-note guard", () => {
    // That guard exists to avoid billing a chat turn that would only restate
    // the import card. Auto Thesis is not a chat turn — dropping the stash
    // here silently downgraded "write my whole thesis" to a normal chat.
    stashAnalyzeIntent("p-files-only", {
      note: "", attachments: [{ upload_id: "u1", filename: "data.xlsx" } as never],
      preseeded: true, autoThesis: true,
    });
    expect(readAnalyzeIntent("p-files-only")).toMatchObject({ autoThesis: true });
  });
});
