/**
 * The M3 slice shows the questionnaire.
 *
 * Regression: the panel read only `questionnaire_text` — the legacy string from
 * the orchestrator schema — while the agent writes the canonical `instrument`
 * key (agent/m3_contract.py). Every agent-authored project therefore had a
 * questionnaire sitting in the store that the right-hand panel silently
 * dropped.
 */
import { describe, expect, test } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { LocaleProvider } from "@/app/lib/i18n/LocaleProvider";
import { M3Body, countConstructs, groupItemsByConstruct } from "./ModuleSlices";

function renderEn(ui: React.ReactElement) {
  return render(<LocaleProvider initialLocale="en" hasCookie>{ui}</LocaleProvider>);
}

const INSTRUMENT = {
  preamble: "Please rate how much you agree with each statement.",
  items: [
    { id: "PU1", text: "Using the system improves my performance.",
      construct: "Perceived Usefulness", scale: "Likert 5" },
    { id: "PU2", text: "I find the system useful.",
      construct: "Perceived Usefulness", scale: "Likert 5", reverse_coded: true },
    { id: "INT1", text: "I intend to keep using the system.",
      construct: "Intention", scale: "Likert 5" },
    { id: "AC1", text: "Please select 'strongly agree' for this item.",
      attention_check: true },
  ],
};

describe("groupItemsByConstruct", () => {
  test("groups by construct in first-appearance order", () => {
    const groups = groupItemsByConstruct(INSTRUMENT.items);
    expect(groups.map((g) => g.construct)).toEqual([
      "Perceived Usefulness", "Intention", "Ungrouped",
    ]);
    expect(groups[0].items).toHaveLength(2);
  });

  test("untagged items land in a trailing bucket instead of vanishing", () => {
    const groups = groupItemsByConstruct([{ text: "no construct" }]);
    expect(groups).toHaveLength(1);
    expect(groups[0].construct).toBe("Ungrouped");
  });

  test("countConstructs ignores the untagged ones", () => {
    expect(countConstructs(INSTRUMENT.items)).toBe(2);
    expect(countConstructs([{ text: "x" }])).toBe(0);
  });
});

describe("M3Body questionnaire row", () => {
  test("summarises a structured instrument by items and constructs", () => {
    renderEn(<M3Body data={{ instrument: INSTRUMENT }} />);
    expect(screen.getByText(/4 items · 2 constructs/)).toBeTruthy();
  });

  test("opens the questionnaire grouped by construct", () => {
    renderEn(<M3Body data={{ instrument: INSTRUMENT }} />);
    fireEvent.click(screen.getByText(/4 items · 2 constructs/));

    expect(screen.getByText(INSTRUMENT.preamble)).toBeTruthy();
    expect(screen.getByText("Perceived Usefulness")).toBeTruthy();
    expect(screen.getByText("Intention")).toBeTruthy();
    expect(screen.getByText(/Using the system improves my performance/)).toBeTruthy();
    // Item metadata a student needs before fielding the survey.
    expect(screen.getAllByText("reverse").length).toBe(1);
    expect(screen.getAllByText("attention").length).toBe(1);
  });

  test("an instrument alone is enough to render M3 — no methodology required", () => {
    renderEn(<M3Body data={{ instrument: INSTRUMENT }} />);
    expect(screen.queryByText(/No M3 data committed yet/)).toBeNull();
  });

  test("legacy questionnaire_text still renders as raw text", () => {
    renderEn(<M3Body data={{ questionnaire_text: "Q1. How old are you?" }} />);
    const row = screen.getByText(/words · click to view/);
    fireEvent.click(row);
    expect(screen.getByText(/Q1. How old are you\?/)).toBeTruthy();
  });

  test("structured items win over a legacy string when both exist", () => {
    renderEn(<M3Body data={{ instrument: INSTRUMENT,
                           questionnaire_text: "stale legacy text" }} />);
    expect(screen.getByText(/4 items · 2 constructs/)).toBeTruthy();
    expect(screen.queryByText(/words · click to view/)).toBeNull();
  });

  test("an instrument carrying only unparsed raw text falls back to it", () => {
    renderEn(<M3Body data={{ instrument: { raw: "unparsed upload body" } }} />);
    fireEvent.click(screen.getByText(/words · click to view/));
    expect(screen.getByText(/unparsed upload body/)).toBeTruthy();
  });

  test("spec-only instrument (constructs + counts, no item text) still shows questionnaire row", () => {
    const SPEC = {
      scale: "Five-point Likert scale",
      source: "User-provided bilingual questionnaire in attached Word document",
      language: "vi-en",
      constructs: ["EXP", "ATT", "DEC"],
      screening_criteria: ["Uses social media frequently"],
      items_per_construct: { EXP: 5, ATT: 5, DEC: 5 },
    };
    renderEn(<M3Body data={{ methodology: { paradigm: "positivist" }, instrument: SPEC }} />);
    expect(screen.getAllByText(/Five-point Likert scale/).length).toBeGreaterThan(0);
    expect(screen.getByText(/3 constructs · 15 items · Five-point Likert scale/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /questionnaire/i }));
    expect(screen.getByText(/Item wording is not in the project state yet/)).toBeTruthy();
    expect(screen.getByText(/EXP: 5 items/)).toBeTruthy();
    expect(screen.getByText(/Uses social media frequently/)).toBeTruthy();
  });

  test("still empty when M3 has nothing at all", () => {
    renderEn(<M3Body data={{}} />);
    expect(screen.getByText(/No M3 data committed yet|Chưa có dữ liệu M3/)).toBeTruthy();
  });
});
