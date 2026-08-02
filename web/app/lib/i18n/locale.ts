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

export const DEFAULT_LOCALE: Locale = "en";

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

/** Look up one string. Falls back to English, then to the key itself. */
export function translate(locale: Locale, key: MessageKey): string {
  return CATALOGUES[locale]?.[key] ?? CATALOGUES.en[key] ?? key;
}
