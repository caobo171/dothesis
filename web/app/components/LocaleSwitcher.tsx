"use client";

import { useLocale } from "../lib/i18n/LocaleProvider";
import { LOCALES } from "../lib/i18n/locale";

/**
 * EN / VI toggle.
 *
 * Always visible rather than hidden behind a settings page: timezone detection
 * is a guess, and a wrong guess leaves a student reading a language they don't
 * want with no obvious way out. The escape hatch has to be where they already
 * are. Their choice writes the cookie and wins over detection forever after.
 */
export function LocaleSwitcher({ className = "" }: { className?: string }) {
  const { locale, setLocale, t } = useLocale();

  return (
    <div
      role="group"
      aria-label={t("lang.label")}
      className={`inline-flex items-center rounded-lg border border-ink-200 p-0.5 ${className}`}
    >
      {LOCALES.map((l) => {
        const active = l === locale;
        return (
          <button
            key={l}
            type="button"
            onClick={() => setLocale(l)}
            aria-pressed={active}
            className={`px-2 py-0.5 text-[11px] font-semibold rounded-md transition-colors ${
              active
                ? "bg-primary-600 text-white"
                : "text-ink-500 hover:text-ink-900 hover:bg-ink-50"
            }`}
          >
            {l.toUpperCase()}
          </button>
        );
      })}
    </div>
  );
}
