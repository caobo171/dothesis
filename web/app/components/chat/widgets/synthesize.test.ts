// web/app/components/chat/widgets/synthesize.test.ts
import { describe, expect, test } from "vitest";
import { synthesizeWidgetSelection } from "./synthesize";
import { summarizeList } from "./synthesize";
import type { ListItem } from "./types";

describe("synthesizeWidgetSelection", () => {
  test("field synthesizes 'I'd like to study X.'", () => {
    expect(synthesizeWidgetSelection("field", "Marketing", "Marketing"))
      .toBe("I'd like to study Marketing.");
  });

  test("research_type synthesizes 'I'll use a X approach.'", () => {
    expect(synthesizeWidgetSelection("research_type", "qualitative", "Qualitative"))
      .toBe("I'll use a qualitative approach.");
  });

  test("unknown field falls back to label", () => {
    expect(synthesizeWidgetSelection("unknown_field", "x", "X")).toBe("X");
  });

  test("research_type uses lowercase label inside the sentence", () => {
    expect(synthesizeWidgetSelection("research_type", "mixed", "Mixed methods"))
      .toBe("I'll use a mixed methods approach.");
  });
});

describe("summarizeList", () => {
  const themes: ListItem[] = [
    { id: "t1", text: "Cách thức lãnh đạo",
      sub_items: [{ id: "s1", text: "Tầm nhìn" }, { id: "s2", text: "Giao tiếp" }] },
    { id: "t2", text: "Biểu hiện gắn kết", sub_items: [] },
  ];

  test("themes produce bulleted message with sub-themes", () => {
    const out = summarizeList(themes, "themes");
    expect(out).toContain("My themes are:");
    expect(out).toContain("- Cách thức lãnh đạo (Sub: Tầm nhìn, Giao tiếp)");
    expect(out).toContain("- Biểu hiện gắn kết");
  });

  test("scale_items group items under construct headers when nested", () => {
    const constructs: ListItem[] = [
      { id: "c0", text: "TL",
        sub_items: [{ id: "c0_i0", text: "TL1: ..." }, { id: "c0_i1", text: "TL2: ..." }] },
    ];
    const out = summarizeList(constructs, "scale_items");
    expect(out).toContain("My scale items:");
    expect(out).toContain("Construct TL:");
    expect(out).toContain("- TL1: ...");
  });

  test("purposive_criteria produces flat bulleted list", () => {
    const crit: ListItem[] = [
      { id: "c0", text: "At SME" }, { id: "c1", text: "6mo+ tenure" },
    ];
    const out = summarizeList(crit, "purposive_criteria");
    expect(out).toContain("My sampling criteria:");
    expect(out).toContain("- At SME");
    expect(out).toContain("- 6mo+ tenure");
  });

  test("interview_guide groups questions by phase via meta", () => {
    const qs: ListItem[] = [
      { id: "q1", text: "[intro] Tell me about your role.",
        sub_items: [], meta: { phase: "intro" } },
      { id: "q2", text: "[main] How does your manager inspire you?",
        sub_items: [{ id: "q2_p0", text: "Can you give an example?" }],
        meta: { phase: "main" } },
    ];
    const out = summarizeList(qs, "interview_guide");
    expect(out).toContain("My interview guide:");
    expect(out).toContain("[intro] Tell me about your role.");
    expect(out).toContain("[main] How does your manager inspire you?");
    expect(out).toContain("Probe: Can you give an example?");
  });

  test("conceptual_model lists paths and hypothesis meta", () => {
    const paths: ListItem[] = [
      { id: "H1", text: "TL → EE", meta: { hypothesis: "H1: TL → EE positive" } },
      { id: "H2", text: "TL → Trust", meta: { hypothesis: "H2: TL → Trust positive" } },
    ];
    const out = summarizeList(paths, "conceptual_model");
    expect(out).toContain("My conceptual model paths:");
    expect(out).toContain("- TL → EE (H1: TL → EE positive)");
    expect(out).toContain("- TL → Trust (H2: TL → Trust positive)");
  });

  test("unknown field falls back to a generic bulleted list", () => {
    const items: ListItem[] = [{ id: "x", text: "anything" }];
    const out = summarizeList(items, "unknown_field");
    expect(out).toContain("- anything");
  });
});
