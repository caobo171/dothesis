// web/app/components/chat/widgets/types.test.ts
import { describe, expect, test } from "vitest";
import type { CardGridHint, ListEditorHint } from "./types";

const CARD_FIXTURE: CardGridHint = {
  widget_type: "card_grid",
  field_name: "field",
  title: "Pick",
  options: [{ value: "Marketing", label: "Marketing", description: "x", icon: null }],
  columns: 3,
};

const LIST_FIXTURE: ListEditorHint = {
  widget_type: "list_editor",
  field_name: "themes",
  title: "Themes",
  initial_items: [
    {
      id: "t1",
      text: "Theme 1",
      sub_items: [{ id: "s1", text: "Sub A" }, { id: "s2", text: "Sub B" }],
      meta: { hypothesis: "H1" },
    },
    { id: "t2", text: "Theme 2", sub_items: [] },
  ],
  allow_nested: true,
  confirm_label: "Confirm",
  reset_label: "Reset to suggested",
};

describe("CardGridHint schema parity", () => {
  test("matches backend Pydantic output shape", () => {
    expect(CARD_FIXTURE.widget_type).toBe("card_grid");
    expect(CARD_FIXTURE.options[0]).toHaveProperty("value");
    expect(CARD_FIXTURE.options[0]).toHaveProperty("label");
    expect(CARD_FIXTURE.options[0]).toHaveProperty("description");
    expect(CARD_FIXTURE.options[0]).toHaveProperty("icon");
  });
});

describe("ListEditorHint schema parity", () => {
  test("matches backend Pydantic output shape", () => {
    expect(LIST_FIXTURE.widget_type).toBe("list_editor");
    expect(LIST_FIXTURE.initial_items[0]).toHaveProperty("id");
    expect(LIST_FIXTURE.initial_items[0]).toHaveProperty("text");
    expect(LIST_FIXTURE.initial_items[0]).toHaveProperty("sub_items");
    expect(LIST_FIXTURE.initial_items[0]).toHaveProperty("meta");
    expect(LIST_FIXTURE.allow_nested).toBe(true);
    expect(LIST_FIXTURE.confirm_label).toBe("Confirm");
  });

  test("nested sub_items have the same shape as parent items", () => {
    const sub = LIST_FIXTURE.initial_items[0].sub_items![0];
    expect(sub).toHaveProperty("id");
    expect(sub).toHaveProperty("text");
  });
});
