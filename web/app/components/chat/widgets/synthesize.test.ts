// web/app/components/chat/widgets/synthesize.test.ts
import { describe, expect, test } from "vitest";
import { synthesizeWidgetSelection } from "./synthesize";

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
