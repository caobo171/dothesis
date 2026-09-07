/**
 * Where this site lives, for anything a crawler reads.
 *
 * Canonicals, the sitemap, JSON-LD `@id`s and the Open Graph `url` all have to
 * agree on one absolute origin or they contradict each other and Google
 * follows none of them. Relative URLs are not an option in any of those
 * places, so the origin has to come from configuration rather than from the
 * incoming request — a request-derived origin flips between the proxy host,
 * localhost and the public domain depending on who is asking.
 *
 * `NEXT_PUBLIC_` prefix because `opengraph-image.tsx` and the metadata helpers
 * are inlined into client-visible output by Next's build.
 */
const RAW_ORIGIN = process.env.NEXT_PUBLIC_SITE_ORIGIN || "http://localhost:3006";

/** No trailing slash, so `${SITE_ORIGIN}${path}` never doubles up. */
export const SITE_ORIGIN = RAW_ORIGIN.replace(/\/+$/, "");

/** The blog's own locale-scoped root. */
export function blogPath(locale: string): string {
  return `/blog/${locale}`;
}

export function postPath(locale: string, slug: string): string {
  return `/blog/${locale}/${slug}`;
}

/** `chu-de` (Vietnamese for "topic") is the public category segment, per spec §6. */
export function categoryPath(locale: string, slug: string): string {
  return `/blog/${locale}/chu-de/${slug}`;
}

/**
 * Next's file-convention OG route for a post. It doubles as the listing card's
 * thumbnail: there is no image hosting yet, and a generated card beats both a
 * blank tile and a stock photo that says nothing about the article.
 */
export function ogImagePath(locale: string, slug: string): string {
  return `/blog/${locale}/${slug}/opengraph-image`;
}

/** Page 1 is the bare listing URL — `?page=1` would be a duplicate of it. */
export function listingPath(locale: string, page = 1): string {
  return page > 1 ? `${blogPath(locale)}?page=${page}` : blogPath(locale);
}

export function absoluteUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  return `${SITE_ORIGIN}${path.startsWith("/") ? path : `/${path}`}`;
}
