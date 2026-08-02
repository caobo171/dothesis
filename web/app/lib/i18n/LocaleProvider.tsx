"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { MessageKey } from "./messages/en";
import {
  DEFAULT_LOCALE,
  detectTimeZone,
  localeFromTimeZone,
  readLocaleCookie,
  translate,
  writeLocaleCookie,
  type Locale,
} from "./locale";

type LocaleContextValue = {
  locale: Locale;
  t: (key: MessageKey) => string;
  setLocale: (next: Locale) => void;
};

const LocaleContext = createContext<LocaleContextValue | null>(null);

/**
 * Provides the active locale + t().
 *
 * `initialLocale` comes from the cookie, read server-side, so the server and the
 * first client render agree — that is what keeps hydration clean. Detection only
 * ever runs when there is NO cookie yet.
 */
export function LocaleProvider({
  initialLocale = DEFAULT_LOCALE,
  hasCookie = false,
  children,
}: {
  initialLocale?: Locale;
  /** Whether the request already carried a locale cookie. */
  hasCookie?: boolean;
  children: ReactNode;
}) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  const setLocale = useCallback((next: Locale) => {
    writeLocaleCookie(next);
    setLocaleState(next);
    // Deliberately NOT router.refresh(): every consumer reads from this
    // context, so a state update repaints the whole tree already. Refreshing
    // would round-trip the server for markup we can produce locally.
  }, []);

  // First visit only. The server rendered DEFAULT_LOCALE and so did our first
  // client render — swapping here, after mount, is a normal state update rather
  // than a hydration mismatch. The cookie means this never runs again, so the
  // brief English flash is once-per-browser, not once-per-visit.
  useEffect(() => {
    if (hasCookie) return;
    if (typeof document !== "undefined" && readLocaleCookie(document.cookie)) return;
    const detected = localeFromTimeZone(detectTimeZone());
    writeLocaleCookie(detected);
    if (detected !== locale) setLocaleState(detected);
    // `locale` intentionally omitted: this must run once on mount, not on every
    // later language change (which would fight the switcher).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasCookie]);

  // Keep <html lang> honest — screen readers and browser translation both key
  // off it, and it is wrong the moment the locale changes without this.
  useEffect(() => {
    if (typeof document !== "undefined") document.documentElement.lang = locale;
  }, [locale]);

  const value = useMemo<LocaleContextValue>(
    () => ({ locale, setLocale, t: (key: MessageKey) => translate(locale, key) }),
    [locale, setLocale],
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale(): LocaleContextValue {
  const ctx = useContext(LocaleContext);
  if (!ctx) {
    throw new Error("useLocale must be used inside <LocaleProvider>");
  }
  return ctx;
}

/** Shorthand for the common case: `const t = useT();` */
export function useT(): (key: MessageKey) => string {
  return useLocale().t;
}
