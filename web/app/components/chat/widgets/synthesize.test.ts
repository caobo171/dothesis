// web/app/components/chat/widgets/synthesize.test.ts
import { describe, expect, test } from "vitest";
import { synthesizeWidgetSelection } from "./synthesize";
import { summarizeList, summarizeFlowChart } from "./synthesize";
import type { FlowChartEdge, FlowChartNode, ListItem } from "./types";

describe("synthesizeWidgetSelection", () => {
  test("field synthesizes 'I'd like to study X.'", () => {
    expect(synthesizeWidgetSelection("field", "Marketing", "Marketing"))
      .toBe("I'd like to study Marketing.");
  });

  test("research_type synthesizes 'I'll use a X approach.'", () => {
    expect(synthesizeWidgetSelection("research_type", "quantitative", "Quantitative"))
      .toBe("I'll use a quantitative approach.");
  });

  test("unknown field falls back to label", () => {
    expect(synthesizeWidgetSelection("unknown_field", "x", "X")).toBe("X");
  });

  test("research_type uses lowercase label inside the sentence", () => {
    expect(synthesizeWidgetSelection("research_type", "survey", "Cross-sectional survey"))
      .toBe("I'll use a cross-sectional survey approach.");
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

  test("selected_gap_ids: free-text from Other routes to add_custom_gap", () => {
    // W5: phase3 Other card opens a typed input. Free text should not be
    // formatted as 'gap <text>' (the intent regex needs digits) — wrap it
    // unambiguously so the LLM classifier picks add_custom_gap.
    expect(synthesizeWidgetSelection(
      "selected_gap_ids",
      "lack of cross-cultural validation",
      "lack of cross-cultural validation",
    )).toBe("Add a new gap: lack of cross-cultural validation.");
  });

  test("familiarize_choice: free-text from Other becomes a refinement note", () => {
    // W5: phase1 Other opens an input; the typed value must NOT match the
    // preset switch arms — route to a 'something else' sentence so the
    // intent classifier picks refine.
    expect(synthesizeWidgetSelection(
      "familiarize_choice",
      "use these papers but also search journal X",
      "use these papers but also search journal X",
    )).toBe(
      "Something else for the literature step: use these papers but also "
      + "search journal X.");
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

  test("reference_verify: yes maps to a plain affirmative", () => {
    expect(synthesizeWidgetSelection(
      "reference_verify", "yes", "Yes — page is correct",
    )).toBe("Yes, the page is correct.");
  });

  test("reference_verify: skip / skip_all are spelled out for the classifier", () => {
    expect(synthesizeWidgetSelection(
      "reference_verify", "skip", "Skip — can't verify",
    )).toBe("Skip this reference.");
    expect(synthesizeWidgetSelection(
      "reference_verify", "skip_all", "Skip all remaining",
    )).toBe("Skip all remaining references.");
  });

  test("reference_verify: Other-typed page number becomes 'correct page N'", () => {
    // The backend regex is `page\s+(\d+)`. The user typed '120' or 'p. 120';
    // either way the synthesizer must wrap it to match.
    expect(synthesizeWidgetSelection(
      "reference_verify", "120", "120",
    )).toBe("The correct page is page 120.");
    expect(synthesizeWidgetSelection(
      "reference_verify", "p. 87", "p. 87",
    )).toBe("The correct page is page 87.");
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

  test("steps without thresholds omit the em-dash", () => {
    const items: ListItem[] = [{ id: "s0", text: "Step One", meta: {} }];
    const out = summarizeList(items, "analysis_outline");
    expect(out).toContain("1. Step One");
    expect(out).not.toContain("Step One —");
  });
});


describe("summarizeFlowChart — merged conceptual_model widget", () => {
  // Design merge (2026-06): conceptual_model widget now ships nodes (with
  // their Likert items attached) + edges (hypothesis paths). The natural-
  // language summary must carry BOTH halves so the backend LLM extractor
  // can rebuild the {nodes:[{label, questions}], edges:[{...}]} shape from
  // the chat message text alone (the structured JSON value is also sent
  // but the extractor reads the message body, mirroring summarizeList).
  const nodes: FlowChartNode[] = [
    { id: "n0", label: "TL",
      questions: ["My supervisor inspires me.",
                  "My supervisor articulates a clear vision."] },
    { id: "n1", label: "EE", questions: ["I feel engaged at work."] },
    { id: "n2", label: "Trust", questions: [] },
  ];
  const edges: FlowChartEdge[] = [
    { id: "H1", source: "n0", target: "n1",
      hypothesis: "H1: TL positively affects EE", effect_type: "positive" },
    { id: "H2", source: "n0", target: "n2",
      hypothesis: "H2: TL builds Trust", effect_type: "positive" },
  ];

  test("emits a labeled paths section + per-construct items section", () => {
    const out = summarizeFlowChart(nodes, edges, "conceptual_model");
    // Top-line header that pairs with the existing 'My ...' convention
    // (objectives, scale_items, ...) so the M3 extractor recognises
    // the message as a final-state submission rather than a clarification.
    expect(out.startsWith("My conceptual model:")).toBe(true);

    // Paths section — must resolve source/target ids back to labels so the
    // extractor sees construct names, not internal ids.
    expect(out).toContain("Paths:");
    expect(out).toContain("- TL → EE (H1: TL positively affects EE)");
    expect(out).toContain("- TL → Trust (H2: TL builds Trust)");

    // Items section — one header per construct that has at least one question;
    // empty-question constructs are skipped (mirrors the prior scale_items
    // formatter which only emitted populated constructs).
    expect(out).toContain("Scale items:");
    expect(out).toContain("Construct TL:");
    expect(out).toContain("- My supervisor inspires me.");
    expect(out).toContain("- My supervisor articulates a clear vision.");
    expect(out).toContain("Construct EE:");
    expect(out).toContain("- I feel engaged at work.");
    // Trust has no questions yet — must NOT appear as a Construct header.
    expect(out).not.toContain("Construct Trust:");
  });

  test("negative effect_type is tagged inline so direction round-trips", () => {
    const negEdges: FlowChartEdge[] = [
      { id: "H3", source: "n0", target: "n1",
        hypothesis: "H3: TL reduces burnout", effect_type: "negative" },
    ];
    const out = summarizeFlowChart(nodes, negEdges, "conceptual_model");
    // Direction tag rides alongside the path so the M3 LLM extractor knows
    // it's a negative hypothesis even when the hypothesis text itself is
    // ambiguous. Positive is the default and stays unlabeled to keep the
    // chat message readable.
    expect(out).toContain("- TL → EE [negative] (H3: TL reduces burnout)");
  });

  test("edges whose endpoints aren't in nodes use the raw id as a fallback", () => {
    // Defensive: if the user dragged a temporary edge to an as-yet-unmapped
    // id, the summary still emits something parseable rather than throwing.
    const out = summarizeFlowChart(
      nodes,
      [{ id: "Hx", source: "ghost", target: "n1", hypothesis: "",
         effect_type: "positive" }],
      "conceptual_model",
    );
    expect(out).toContain("- ghost → EE");
  });

  test("empty model still emits the header so the backend sees a final-state submission", () => {
    const out = summarizeFlowChart([], [], "conceptual_model");
    expect(out.startsWith("My conceptual model:")).toBe(true);
  });
});
