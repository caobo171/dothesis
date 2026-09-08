import { describe, expect, test } from "vitest";

import { alternateLanguages, otherLocale } from "./hreflang";

describe("hreflang", () => {
  test("names the other edition", () => {
    expect(otherLocale("vi")).toBe("en");
    expect(otherLocale("en")).toBe("vi");
  });

  test("declares both editions and points x-default at the Vietnamese one", () => {
    expect(
      alternateLanguages({
        vi: "http://localhost:3006/blog/vi",
        en: "http://localhost:3006/blog/en",
      }),
    ).toEqual({
      vi: "http://localhost:3006/blog/vi",
      en: "http://localhost:3006/blog/en",
      "x-default": "http://localhost:3006/blog/vi",
    });
  });

  test("a page with no verified counterpart declares nothing at all", () => {
    // Not `{vi: url}`: a page pointing hreflang at itself is not an annotation,
    // and the whole point of this module is that an unverified pair is worse
    // than none — Google drops a cluster whose alternate 404s.
    expect(alternateLanguages({ vi: "http://localhost:3006/blog/vi" })).toBeUndefined();
    expect(alternateLanguages({})).toBeUndefined();
  });

  test("region-free tags, so the diaspora is not excluded from the vi edition", () => {
    const languages = alternateLanguages({ vi: "https://x/vi", en: "https://x/en" }) ?? {};
    expect(Object.keys(languages).sort()).toEqual(["en", "vi", "x-default"]);
  });
});
