/**
 * hreflang, and the rule that a pair has to be verified before it is declared.
 *
 * Two language editions of one page have to name each other, or Google treats
 * them as competitors for the same query and picks one — usually the older,
 * which here is always the Vietnamese. `alternates.languages` in each route's
 * metadata is how Next emits that.
 *
 * The dangerous half is the pairing. hreflang pointing at a URL that 404s is
 * worse than no hreflang at all: Google drops the whole annotation cluster and
 * says nothing about it in Search Console. Slugs are per-locale
 * (`uq_blog_posts_locale_slug`) and a translation is published on its own
 * schedule, so "the same page in the other language" is never something this
 * code may assume — every helper here takes a URL the caller has already
 * checked against the API, and a set with only one language in it produces no
 * annotation at all.
 */
import { type Locale } from "../../lib/i18n/locale";

/**
 * Language-only tags, no region.
 *
 * `vi-VN` would tell Google this page is for Vietnamese speakers *in Vietnam*
 * and quietly exclude the diaspora — a real slice of the readership, and one
 * that searches in Vietnamese from a US or Australian IP. The English edition
 * has no country at all: it is the international edition, not a US one.
 */
export const HREFLANG: Record<Locale, string> = { vi: "vi", en: "en" };

/** The other edition. There are exactly two, so "the other one" is definite. */
export function otherLocale(locale: Locale): Locale {
  return locale === "vi" ? "en" : "vi";
}

/**
 * `alternates.languages`, or undefined when there is nothing to declare.
 *
 * Undefined rather than a self-only map on purpose: an hreflang set that names
 * one language is a page pointing at itself, which is not an annotation and
 * only adds bytes. Callers pass entries they have verified exist.
 *
 * `x-default` goes to the Vietnamese URL when there is one. It is the answer to
 * "a reader we have no language signal for", and this product is
 * Vietnamese-primary — `DEFAULT_LOCALE` is `vi` and `/blog` itself redirects
 * there, so anything else would contradict a redirect Google already follows.
 */
export function alternateLanguages(
  urlByLocale: Partial<Record<Locale, string>>,
): Record<string, string> | undefined {
  const entries = (Object.entries(urlByLocale) as Array<[Locale, string | undefined]>).filter(
    (entry): entry is [Locale, string] => Boolean(entry[1]),
  );
  if (entries.length < 2) return undefined;

  const languages: Record<string, string> = {};
  for (const [locale, url] of entries) languages[HREFLANG[locale]] = url;
  languages["x-default"] = urlByLocale.vi ?? entries[0][1];
  return languages;
}
