import { describe, expect, test } from "vitest";

import {
  DEFAULT_LOCALE,
  LOCALE_COOKIE,
  isLocale,
  localeFromTimeZone,
  readLocaleCookie,
  translate,
} from "./locale";
import { en } from "./messages/en";
import { vi } from "./messages/vi";

describe("localeFromTimeZone", () => {
  test("Vietnam timezones select Vietnamese", () => {
    expect(localeFromTimeZone("Asia/Ho_Chi_Minh")).toBe("vi");
    // Deprecated alias still reported by some older browsers / JVM stacks.
    expect(localeFromTimeZone("Asia/Saigon")).toBe("vi");
  });

  test("everything else falls back to the default", () => {
    for (const tz of ["UTC", "Europe/London", "America/New_York", "Asia/Bangkok"]) {
      expect(localeFromTimeZone(tz)).toBe(DEFAULT_LOCALE);
    }
  });

  test("a missing timezone does not throw", () => {
    // Intl can throw in locked-down environments; detectTimeZone returns
    // undefined there and we must still resolve to something renderable.
    expect(localeFromTimeZone(undefined)).toBe(DEFAULT_LOCALE);
    expect(localeFromTimeZone(null)).toBe(DEFAULT_LOCALE);
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
