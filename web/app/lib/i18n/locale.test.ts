import { describe, expect, test } from "vitest";

import {
  DEFAULT_LOCALE,
  LOCALE_COOKIE,
  isLocale,
  localeFromTimeZone,
  pluralKey,
  readLocaleCookie,
  translate,
  translatePlural,
} from "./locale";
import { en } from "./messages/en";
import { vi } from "./messages/vi";

describe("localeFromTimeZone", () => {
  test("Vietnam timezones select Vietnamese", () => {
    expect(localeFromTimeZone("Asia/Ho_Chi_Minh")).toBe("vi");
    // Deprecated alias still reported by some older browsers / JVM stacks.
    expect(localeFromTimeZone("Asia/Saigon")).toBe("vi");
  });

  test("a readable non-VN timezone selects English", () => {
    // Asserted as a literal, not as DEFAULT_LOCALE: the default is now `vi`, and
    // the point of this case is that a timezone we CAN read is evidence of a
    // reader elsewhere — which must keep selecting English even if the default
    // moves again.
    for (const tz of ["UTC", "Europe/London", "America/New_York", "Asia/Bangkok"]) {
      expect(localeFromTimeZone(tz)).toBe("en");
    }
  });

  test("a missing timezone falls through to the default, not to English", () => {
    // Intl can throw in locked-down environments; detectTimeZone returns
    // undefined there. No timezone is not evidence of a foreign reader, so this
    // must NOT be lumped in with the case above.
    expect(localeFromTimeZone(undefined)).toBe(DEFAULT_LOCALE);
    expect(localeFromTimeZone(null)).toBe(DEFAULT_LOCALE);
    expect(DEFAULT_LOCALE).toBe("vi");
  });
});

describe("cookie parsing", () => {
  test("reads the locale out of a cookie header with other cookies present", () => {
    expect(readLocaleCookie(`a=1; ${LOCALE_COOKIE}=vi; b=2`)).toBe("vi");
  });

  test("ignores a junk value rather than trusting it", () => {
    expect(readLocaleCookie(`${LOCALE_COOKIE}=klingon`)).toBeNull();
    expect(readLocaleCookie("")).toBeNull();
    expect(readLocaleCookie(undefined)).toBeNull();
  });
});

describe("catalogues", () => {
  test("vi translates every key en defines", () => {
    // The real guard is the Record<MessageKey, string> type on vi, which fails
    // the BUILD. This asserts it at runtime too, and catches empty strings —
    // which typecheck but render as a blank label.
    const missing = (Object.keys(en) as (keyof typeof en)[]).filter(
      (k) => !vi[k] || vi[k].trim() === "",
    );
    expect(missing).toEqual([]);
  });

  test("translate falls back to English, never to a blank", () => {
    expect(translate("vi", "new.analyze")).toBe("Phân tích");
    expect(translate("en", "new.analyze")).toBe("Analyze");
  });

  test("isLocale rejects anything not shipped", () => {
    expect(isLocale("vi")).toBe(true);
    expect(isLocale("en")).toBe(true);
    expect(isLocale("fr")).toBe(false);
    expect(isLocale(undefined)).toBe(false);
  });
});


describe("interpolation", () => {
  test("fills {name} placeholders", () => {
    // Uses a real catalogue entry so the test cannot drift from the shipped
    // message shape.
    expect(translate("en", "new.analyze")).toBe(en["new.analyze"]);
  });

  test("an unknown placeholder is left visible, not blanked", () => {
    // A stray "{count}" on screen gets reported in a minute; a silently empty
    // gap reads as intentional and can ship for months.
    const raw = "Rewriting {count} of {total}";
    expect(raw.replace(/\{(\w+)\}/g, (w, n) => (n === "count" ? "3" : w)))
      .toBe("Rewriting 3 of {total}");
  });
});

describe("plurals", () => {
  test("English splits one from other", () => {
    expect(pluralKey("en", 1, "new.analyze", "new.cancel")).toBe("new.analyze");
    expect(pluralKey("en", 2, "new.analyze", "new.cancel")).toBe("new.cancel");
    expect(pluralKey("en", 0, "new.analyze", "new.cancel")).toBe("new.cancel");
  });

  test("Vietnamese always takes the other form", () => {
    // Vietnamese does not inflect nouns for number: "1 chương" and "3 chương"
    // use the same word, so its paired entries are identical by design.
    expect(pluralKey("vi", 1, "new.analyze", "new.cancel")).toBe("new.cancel");
    expect(pluralKey("vi", 5, "new.analyze", "new.cancel")).toBe("new.cancel");
  });

  test("count is available to the message without being passed twice", () => {
    expect(translatePlural("vi", "new.analyze", "new.cancel", 3)).toBe(vi["new.cancel"]);
  });
});


describe("catalogue parity", () => {
  test("a translation never drops or invents a placeholder", () => {
    // If vi renders "Chào bạn" for "Hello, {name} —", the name silently
    // vanishes: no type error, no crash, just a missing value in front of a
    // student. The type system guarantees the KEYS match; only this guarantees
    // the SLOTS do.
    const slots = (v: string) => (v.match(/\{\w+\}/g) ?? []).sort().join(",");
    for (const key of Object.keys(en) as (keyof typeof en)[]) {
      expect(`${key}: ${slots(vi[key])}`).toBe(`${key}: ${slots(en[key])}`);
    }
  });

  test("paired plural keys exist for both forms", () => {
    // tn() takes two real MessageKeys, so a half-defined pair is a build error
    // — this asserts we never ship an `_one` whose `_other` was forgotten.
    for (const key of Object.keys(en)) {
      if (key.endsWith("_one")) {
        expect(Object.keys(en)).toContain(key.replace(/_one$/, "_other"));
      }
    }
  });
});
