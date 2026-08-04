/**
 * Locale resolution: timezone -> locale, plus the cookie that makes it stick.
 *
 * Pure functions only, no React and no `document` at module scope, so this file
 * is importable from a server component (to read the cookie during SSR) and from
 * the client bootstrap alike.
 */
import { en, type MessageKey } from "./messages/en";
import { vi } from "./messages/vi";

export const LOCALES = ["en", "vi"] as const;
export type Locale = (typeof LOCALES)[number];

// Vietnamese, not English (2026-08-04). The product is Vietnamese-primary: a
// student on a VPN, a travelling laptop, or a locked-down browser where Intl
// throws used to land on an English UI for a Vietnamese-language thesis tool.
// The default is what you get when we know nothing, so it should be the
// likeliest reader — English is now an explicit signal, not the fallback.
export const DEFAULT_LOCALE: Locale = "vi";

/** Cookie name. Read server-side on every request; written once client-side. */
export const LOCALE_COOKIE = "dothesis_lang";

/** One year — a student's language preference is not a session-scoped thing. */
const COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

const CATALOGUES: Record<Locale, Record<MessageKey, string>> = {
  en: en as unknown as Record<MessageKey, string>,
  vi,
};

export function isLocale(v: string | undefined | null): v is Locale {
  return !!v && (LOCALES as readonly string[]).includes(v);
}

/**
 * Map an IANA timezone to a locale.
 *
 * Timezone rather than Accept-Language on purpose: Accept-Language reflects the
 * OS/browser language, and a large share of Vietnamese students run their
 * machines in English — so Accept-Language would hand them an English UI even
 * though they'd rather read Vietnamese. Where the machine physically IS turns
 * out to be the better signal for this product.
 *
 * Asia/Saigon is the deprecated alias for Asia/Ho_Chi_Minh; some older browsers
 * and JVM-derived stacks still report it, so both map to vi.
 */
const VI_TIMEZONES = new Set(["Asia/Ho_Chi_Minh", "Asia/Saigon"]);

export function localeFromTimeZone(tz: string | undefined | null): Locale {
  if (tz && VI_TIMEZONES.has(tz)) return "vi";
  // A timezone we can read and that isn't Vietnam is real evidence of a reader
  // elsewhere, so it selects English. NO timezone is not evidence of anything —
  // that falls through to the default, which is why the two cases are separate
  // rather than one `return tz ? "en" : "vi"`.
  if (tz) return "en";
  return DEFAULT_LOCALE;
}

/** Reads the browser's timezone. Client-only — returns undefined on the server. */
export function detectTimeZone(): string | undefined {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    // Intl is present everywhere we support, but a locked-down environment can
    // throw here. Falling back to the default beats crashing the layout.
    return undefined;
  }
}

/** Parse the locale out of a raw `document.cookie` / request cookie header. */
export function readLocaleCookie(cookieHeader: string | undefined | null): Locale | null {
  if (!cookieHeader) return null;
  for (const part of cookieHeader.split(";")) {
    const [k, ...rest] = part.trim().split("=");
    if (k === LOCALE_COOKIE) {
      const v = decodeURIComponent(rest.join("="));
      return isLocale(v) ? v : null;
    }
  }
  return null;
}

export function writeLocaleCookie(locale: Locale): void {
  // SameSite=Lax so it survives normal navigation; not HttpOnly because the
  // client bootstrap is what sets it and there is nothing sensitive in it.
  document.cookie = `${LOCALE_COOKIE}=${locale}; path=/; max-age=${COOKIE_MAX_AGE}; samesite=lax`;
}

/** Values a message can interpolate. Numbers are stringified by the caller's
 *  locale rules only where a component formats them — `t` does not guess. */
export type TParams = Record<string, string | number>;

const _PLACEHOLDER = /\{(\w+)\}/g;

/**
 * Substitute `{name}` placeholders.
 *
 * Interpolation rather than concatenation at the call site is the whole reason
 * this exists: `count + " paragraphs"` hard-codes English word order, and the
 * moment a language puts its number elsewhere the sentence is wrong with no
 * compiler to catch it. Keeping the variable INSIDE the translated string lets
 * each locale place it wherever its grammar wants.
 *
 * An unknown placeholder is left visible rather than blanked. A stray
 * "{count}" on screen is a loud bug someone reports in a minute; a silently
 * empty gap reads as intentional and can ship for months.
 */
function interpolate(raw: string, params?: TParams): string {
  if (!params) return raw;
  return raw.replace(_PLACEHOLDER, (whole, name: string) =>
    name in params ? String(params[name]) : whole);
}

/** Look up one string. Falls back to English, then to the key itself. */
export function translate(locale: Locale, key: MessageKey, params?: TParams): string {
  const raw = CATALOGUES[locale]?.[key] ?? CATALOGUES.en[key] ?? key;
  return interpolate(raw, params);
}

/**
 * Pick between a singular and a plural key.
 *
 * Vietnamese does not inflect nouns for number — "3 chương" and "1 chương" use
 * the same word — so it always takes the `other` form, and its catalogue
 * entries for the pair are identical by design rather than by oversight.
 * English needs the split. Both keys are real MessageKeys, so a missing
 * translation is a BUILD error; deriving "key_one"/"key_other" by string
 * concatenation would have moved that failure to runtime.
 */
export function pluralKey(
  locale: Locale, count: number, one: MessageKey, other: MessageKey,
): MessageKey {
  if (locale === "vi") return other;
  return Math.abs(count) === 1 ? one : other;
}

/** Plural-aware lookup. `count` is always available to the message as {count}. */
export function translatePlural(
  locale: Locale,
  one: MessageKey,
  other: MessageKey,
  count: number,
  params?: TParams,
): string {
  return translate(locale, pluralKey(locale, count, one, other), { count, ...params });
}
