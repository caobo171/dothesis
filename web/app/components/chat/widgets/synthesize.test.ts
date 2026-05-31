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

  test("selected_gap_ids synthesizes a 'use gap N and gap M' sentence", () => {
    // W2: multi-select widget sends value="1,3", but the M2 intent classifier
    // expects the 'gap N' tokens (regex \bgap\s*(\d+)\b). Synthesize a sentence
    // that includes them explicitly so the click round-trips into the select
    // action without changing the backend parser.
    expect(synthesizeWidgetSelection(
      "selected_gap_ids", "1,3", "No SME context, Mediator untested",
    )).toBe("I'll use gap 1 and gap 3.");
  });

  test("selected_gap_ids with a single pick still uses 'gap N'", () => {
    expect(synthesizeWidgetSelection("selected_gap_ids", "2", "Mediator untested"))
      .toBe("I'll use gap 2.");
  });

  test("familiarize_choice: ai_search picks the AI search branch", () => {
    // W1: phase 1's intent classifier maps 'skip' = use AI search. Synthesize
    // a sentence that nudges the model toward that mapping unambiguously.
    expect(synthesizeWidgetSelection(
      "familiarize_choice", "ai_search", "Let AI search for citations",
    )).toBe("Please use AI search to find citations for me.");
  });

  test("research_state_confirm: confirm value maps to a clear yes phrase", () => {
    expect(synthesizeWidgetSelection(
      "research_state_confirm", "confirm", "Confirm — this synthesis works",
    )).toBe("Yes, this synthesis works — let's continue.");
  });

  test("research_state_confirm: navigate value sends a go-back sentence", () => {
    expect(synthesizeWidgetSelection(
      "research_state_confirm", "navigate", "Go back to literature search",
    )).toBe("Go back to the literature search step.");
  });

  test("research_state_confirm: free-text from Other becomes a Refine sentence", () => {
    // After typing in the Other input the widget calls onSelect with the
    // typed text as both value and label. The synthesizer must route that
    // into the 'refine' intent — not be mistaken for the preset 'confirm'.
    expect(synthesizeWidgetSelection(
      "research_state_confirm",
      "focus on Self-Determination Theory",
      "focus on Self-Determination Theory",
    )).toBe("Refine the synthesis: focus on Self-Determination Theory.");
  });

  test("familiarize_choice: use_papers confirms uploaded sources", () => {
    expect(synthesizeWidgetSelection(
      "familiarize_choice", "use_papers", "Use my 2 uploaded papers",
    )).toBe("Yes, use my uploaded papers as sources.");
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

  test("objectives lead with a labeled header so _extract_answer can parse them", () => {
    const items: ListItem[] = [
      { id: "obj_0", text: "Measure the correlation between TikTok use and academic motivation." },
      { id: "obj_1", text: "Examine moderating effects of content type." },
    ];
    const out = summarizeList(items, "objectives");
    // Header is the load-bearing bit — without it the bare bullets used to
    // read as a clarifying question and looped the conversation.
    expect(out.split("\n")[0]).toBe("My research objectives:");
    expect(out).toContain("- Measure the correlation between TikTok use and academic motivation.");
    expect(out).toContain("- Examine moderating effects of content type.");
  });

  test("research_questions use the labeled header pattern too", () => {
    const items: ListItem[] = [
      { id: "rq_0", text: "How does TikTok use affect academic motivation?" },
      { id: "rq_1", text: "What content types drive the strongest engagement?" },
    ];
    const out = summarizeList(items, "research_questions");
    expect(out.split("\n")[0]).toBe("My research questions:");
    expect(out).toContain("- How does TikTok use affect academic motivation?");
    expect(out).toContain("- What content types drive the strongest engagement?");
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

describe("summarizeList — SP5 analysis outline fields", () => {
  const outlineItems: ListItem[] = [
    { id: "s0", text: "Descriptive Statistics", meta: {} },
    { id: "s1", text: "Reliability (Cronbach's Alpha)", meta: { thresholds: "α ≥ 0.7" } },
    { id: "s2", text: "Regression Analysis", meta: { thresholds: "VIF < 10" } },
  ];

  test("analysis_outline produces numbered list with thresholds", () => {
    const out = summarizeList(outlineItems, "analysis_outline");
    expect(out).toContain("My analysis outline:");
    expect(out).toContain("1. Descriptive Statistics");
    expect(out).toContain("2. Reliability (Cronbach's Alpha) — α ≥ 0.7");
    expect(out).toContain("3. Regression Analysis — VIF < 10");
  });

  test("outline_quant uses the same format", () => {
    const out = summarizeList(outlineItems, "outline_quant");
    expect(out).toContain("My analysis outline:");
    expect(out).toContain("1. Descriptive Statistics");
  });

  test("outline_qual uses the same format", () => {
    const out = summarizeList(outlineItems, "outline_qual");
    expect(out).toContain("My analysis outline:");
  });

  test("steps without thresholds omit the em-dash", () => {
    const items: ListItem[] = [{ id: "s0", text: "Step One", meta: {} }];
    const out = summarizeList(items, "analysis_outline");
    expect(out).toContain("1. Step One");
    expect(out).not.toContain("Step One —");
  });
});
