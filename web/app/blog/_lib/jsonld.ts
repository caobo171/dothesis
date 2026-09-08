/**
 * Structured-data builders (spec §10).
 *
 * Kept out of the page components and unit-tested, because JSON-LD is the one
 * part of the page nobody looks at: a typo in a `@type` or a date that is not
 * ISO 8601 costs the rich result and there is no visual symptom. The rule
 * followed throughout is that the markup may only describe what the page
 * actually renders — the FAQ block is built from the same `extractFaq` the
 * body is rendered from, so the two cannot disagree.
 */
import type { FullPost } from "./api";
import type { FaqItem } from "./markdown";
import { SITE_ORIGIN, absoluteUrl, postPath } from "./site";

const PUBLISHER = {
  "@type": "Organization",
  name: "DoThesis",
  url: SITE_ORIGIN,
  logo: {
    "@type": "ImageObject",
    url: `${SITE_ORIGIN}/logo-mark.png`,
  },
} as const;

/** BCP 47 for the two locales this site ships. */
function languageTag(locale: string): string {
  return locale === "vi" ? "vi-VN" : "en-US";
}

/** ISO 8601, or undefined — an unparseable date is worse than an absent one. */
function isoOrUndefined(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? undefined : d.toISOString();
}

/**
 * The page's own URL. A post may carry an explicit `canonical_url` (a
 * republished piece, or one that consolidates two older slugs); when it does,
 * every identifier here follows it, otherwise the markup would tell Google the
 * canonical is elsewhere while claiming this URL as the article's `@id`.
 */
export function postUrl(post: Pick<FullPost, "locale" | "slug" | "canonical_url">): string {
  return post.canonical_url || absoluteUrl(postPath(post.locale, post.slug));
}

/** Drop keys whose value is undefined so no empty properties reach the JSON. */
function compact<T extends Record<string, unknown>>(obj: T): T {
  return Object.fromEntries(Object.entries(obj).filter(([, v]) => v !== undefined)) as T;
}

export function blogPostingJsonLd(post: FullPost): Record<string, unknown> {
  const url = postUrl(post);
  const published = isoOrUndefined(post.published_at);
  return compact({
    "@context": "https://schema.org",
    "@type": "BlogPosting",
    "@id": `${url}#article`,
    mainEntityOfPage: { "@type": "WebPage", "@id": url },
    url,
    headline: post.title,
    description: post.meta_description || post.excerpt || undefined,
    inLanguage: languageTag(post.locale),
    datePublished: published,
    // An unedited post still needs dateModified: leaving it out makes Google
    // guess, and it usually guesses the crawl date.
    dateModified: isoOrUndefined(post.updated_at) ?? published,
    // `image_url` is stored root-relative (`/img/blog/x.webp`) because an
    // absolute origin in the database bakes in the environment. Structured
    // data has no page to resolve a relative url against, so it goes through
    // absoluteUrl(), which passes an already-absolute url through untouched.
    image: post.image_url ? [absoluteUrl(post.image_url)] : undefined,
    articleSection: post.category?.display_name || undefined,
    keywords: post.tags?.length ? post.tags.join(", ") : undefined,
    timeRequired: post.reading_time ? `PT${post.reading_time}M` : undefined,
    author: PUBLISHER,
    publisher: PUBLISHER,
  });
}

/**
 * FAQPage markup, or null when the post has no FAQ section.
 *
 * Null rather than an empty `mainEntity`: an FAQPage with no questions is a
 * structured-data error in Search Console, and "this page has no FAQ" is a
 * perfectly ordinary state for the shorter archetypes.
 */
export function faqJsonLd(
  items: FaqItem[],
  post: Pick<FullPost, "locale" | "slug" | "canonical_url">,
): Record<string, unknown> | null {
  if (!items.length) return null;
  const url = postUrl(post);
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "@id": `${url}#faq`,
    mainEntity: items.map((item) => ({
      "@type": "Question",
      name: item.question,
      acceptedAnswer: { "@type": "Answer", text: item.answer },
    })),
  };
}
