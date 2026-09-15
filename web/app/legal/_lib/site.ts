/**
 * The facts every legal and contact page states, in one place.
 *
 * These are not copy. They are claims about a real company, a real inbox and a
 * real effective date, and the three pages have to agree on them — a privacy
 * policy naming one address while the contact page publishes another is the
 * kind of drift that makes both unusable as a legal record.
 *
 * Kept out of the app's i18n catalogue on purpose: an entity name and an email
 * are the same string in every language, and putting them in two catalogues is
 * how one of them goes stale.
 */
import { type Locale } from "../../lib/i18n/locale";

/** The one inbox. Every mailto on every legal page resolves here. */
export const EMAIL = "contact@hiesolution.com";

/** The operator named in the policies, and credited in the landing footer. */
export const ENTITY = "HIE Solution";

export const PRODUCT = "DoThesis";
export const SITE_HOST = "dothesis.com";

/**
 * The "last updated" line on the policies.
 *
 * One constant for both documents because they were written and take effect
 * together. Change it when the TEXT changes — not on a redeploy, and not when
 * only this file moves. A date that advances without the terms advancing is a
 * false statement about when a reader last needed to re-read them.
 */
export const UPDATED = "2026-09-14";

/**
 * The reader-facing date, written the way each language writes dates.
 *
 * `14 tháng 9, 2026` rather than the US `September 14, 2026` for the Vietnamese
 * edition: this is the one date a reader is asked to check, and a format they
 * have to decode is a format they skip.
 */
export function formattedDate(locale: Locale): string {
  const [y, m, d] = UPDATED.split("-").map(Number);
  return locale === "vi"
    ? `${d} tháng ${m}, ${y}`
    : new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-US", {
        year: "numeric",
        month: "long",
        day: "numeric",
        timeZone: "UTC",
      });
}

/** The three documents, as the routes that serve them. */
export type LegalDoc = "privacy" | "terms" | "contact";

/**
 * `/privacy/vi`, not `/vi/privacy`.
 *
 * Matches `blogPath` — the locale is the last segment on every localized URL
 * this site already publishes, and one site with two URL shapes is a site whose
 * links nobody can predict.
 */
export function legalPath(doc: LegalDoc, locale: string): string {
  return `/${doc}/${locale}`;
}

/**
 * A mailto, optionally pre-filled with a subject.
 *
 * The subject is the only sorting this inbox gets — there is no form and no
 * ticketing system behind it — so a message about billing should arrive already
 * saying so.
 */
export function mailto(subject?: string): string {
  return subject ? `mailto:${EMAIL}?subject=${encodeURIComponent(subject)}` : `mailto:${EMAIL}`;
}
