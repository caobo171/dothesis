import { describe, expect, test } from "vitest";
import { activityLabel, TOOL_LABEL_KEYS } from "./activityLabel";
import { translate } from "../../lib/i18n/locale";
import { en } from "../../lib/i18n/messages/en";
import { vi as viMessages } from "../../lib/i18n/messages/vi";

const t = (locale: "vi" | "en") =>
  (key: Parameters<typeof translate>[1]) => translate(locale, key);

describe("activityLabel", () => {
  // headless_entry.py writes `tool: <name>` as the activity text, and that
  // string is a machine fact the partner API reads back as `current`. It is not
  // a sentence for a student: the run screen showed "tool: research_scout" to
  // someone whose thesis is in Vietnamese.
  test("turns a tool id into something a student can read", () => {
    const out = activityLabel("tool: research_scout", t("vi"));
    expect(out).toBe(viMessages["run.tool.research_scout"]);
    expect(out).not.toMatch(/research_scout/);
    expect(out).not.toMatch(/^tool:/);
  });

  test("a tool nobody has translated yet still never leaks its id", () => {
    // The failure mode this guards: someone adds a tool to agent/runtime.py and
    // its internal name appears on a student's screen a release later.
    const out = activityLabel("tool: some_brand_new_tool", t("vi"));
    expect(out).toBe(viMessages["run.tool.unknown"]);
    expect(out).not.toMatch(/some_brand_new_tool/);
  });

  test("passes through activity text that is already a sentence", () => {
    // Not every activity beat is a tool call — "run paused by request" and the
    // M2 scout's own progress lines come through here too.
    expect(activityLabel("42 sources, screening", t("en"))).toBe("42 sources, screening");
  });

  test("survives a malformed beat rather than rendering half of it", () => {
    expect(activityLabel("tool:", t("en"))).toBe(en["run.tool.unknown"]);
    expect(activityLabel("tool:   ", t("en"))).toBe(en["run.tool.unknown"]);
    expect(activityLabel("", t("en"))).toBe("");
  });

  test("every tool the agent can call has a phrase in both languages", () => {
    // The list is checked against agent/runtime.py by hand; this asserts the
    // catalogues stay in step with it, in both locales, so vi never silently
    // falls back to English mid-run.
    for (const key of Object.values(TOOL_LABEL_KEYS)) {
      expect(en[key], `missing en copy for ${key}`).toBeTruthy();
      expect(viMessages[key], `missing vi copy for ${key}`).toBeTruthy();
      expect(viMessages[key]).not.toBe(en[key]);
    }
  });
});
