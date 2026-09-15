/**
 * Sitemap construction, kept out of `app/sitemap.ts` so it can be unit-tested.
 *
 * The sitemap is the blog's only reliable discovery path. The listing paginates
 * and the category pages cap out, so a crawler that never follows a pager past
 * page three would find a fraction of a thousand posts through links alone.
 */
import type { MetadataRoute } from "next";

import { LOCALES } from "../../lib/i18n/locale";
import type { BlogCategory, SitemapEntry } from "./api";
import { SITE_ORIGIN, blogPath, categoryPath, postPath } from "./site";

/**
 * Both editions, always — NOT `localesToList`, which is derived from the posts
 * that happen to exist. The legal pages do not depend on the blog having
 * published anything in a language.
 */
const LEGAL_LOCALES = LOCALES;

/** A date Google will accept, or now — an invalid `lastmod` invalidates the entry. */
function safeDate(value: string | null | undefined): Date {
  if (!value) return new Date();
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? new Date() : d;
}

export function buildBlogSitemap(input: {
  posts: SitemapEntry[];
  categoriesByLocale: Record<string, BlogCategory[]>;
}): MetadataRoute.Sitemap {
  const now = new Date();
  const locales = Object.keys(input.categoriesByLocale);

  const rows: MetadataRoute.Sitemap = [
    // The home of the marketing host, not `/landing`: on dothesis.com `/`
    // renders the landing page and `/landing` 301s to it, so listing the old
    // path would only ask Google to crawl a redirect.
    {
      url: `${SITE_ORIGIN}/`,
      lastModified: now,
      changeFrequency: "monthly",
      priority: 1,
    },
  ];

  // Legal and contact, both editions. Listed unconditionally — unlike a blog
  // post, both language editions of these ship in the same source file, so
  // there is no publishing schedule to wait on and no chance of listing a URL
  // that 404s. They change rarely and rank for nothing, but a crawler that can
  // find them is one signal this is a real operation rather than a parked
  // domain, and it is the same set a payment provider's review looks for.
  for (const doc of ["privacy", "terms", "contact"] as const) {
    for (const locale of LEGAL_LOCALES) {
      rows.push({
        url: `${SITE_ORIGIN}/${doc}/${locale}`,
        lastModified: now,
        changeFrequency: "yearly",
        priority: 0.3,
      });
    }
  }

  for (const locale of locales) {
    rows.push({
      url: `${SITE_ORIGIN}${blogPath(locale)}`,
      lastModified: now,
      changeFrequency: "daily",
      priority: 0.8,
    });
    for (const category of input.categoriesByLocale[locale]) {
      rows.push({
        url: `${SITE_ORIGIN}${categoryPath(locale, category.slug)}`,
        lastModified: now,
        changeFrequency: "weekly",
        priority: 0.7,
      });
    }
  }

  for (const post of input.posts) {
    rows.push({
      url: `${SITE_ORIGIN}${postPath(post.locale, post.slug)}`,
      lastModified: safeDate(post.updated_at),
      changeFrequency: "monthly",
      priority: 0.6,
    });
  }

  return rows;
}

/**
 * Which locales the sitemap covers.
 *
 * Derived from the posts that actually exist, plus `vi` unconditionally so the
 * Vietnamese listing and its nine category pages are listed on day one, before
 * the first tranche of posts goes live.
 */
export function localesToList(posts: SitemapEntry[]): string[] {
  return [...new Set(["vi", ...posts.map((p) => p.locale)])];
}
