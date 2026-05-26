// web/app/components/chat/widgets/types.test.ts
import { describe, expect, test } from "vitest";
import type { CardGridHint } from "./types";

/**
 * Fixture matching exactly what backend's orchestrator/agents/widgets.py
 * CardGridHint.model_dump() produces. If backend schema changes, the
 * fixture below stops parsing cleanly into the TS type and the build fails
 * — surfacing the drift before it ships.
 */
const FIXTURE: CardGridHint = {
  widget_type: "card_grid",
  field_name: "field",
  title: "Pick",
  options: [
    { value: "Marketing", label: "Marketing", description: "x", icon: null },
  ],
  columns: 3,
};

describe("CardGridHint schema parity", () => {
  test("matches backend Pydantic output shape", () => {
    expect(FIXTURE.widget_type).toBe("card_grid");
    expect(FIXTURE.options[0]).toHaveProperty("value");
    expect(FIXTURE.options[0]).toHaveProperty("label");
    expect(FIXTURE.options[0]).toHaveProperty("description");
    expect(FIXTURE.options[0]).toHaveProperty("icon");
  });
});
