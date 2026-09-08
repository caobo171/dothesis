/**
 * Sitemap construction, kept out of `app/sitemap.ts` so it can be unit-tested.
 *
 * The sitemap is the blog's only reliable discovery path. The listing paginates
 * and the category pages cap out, so a crawler that never follows a pager past
 * page three would find a fraction of a thousand posts through links alone.
 */
import type { MetadataRoute } from "next";

import type { BlogCategory, SitemapEntry } from "./api";
import { SITE_ORIGIN, blogPath, categoryPath, postPath } from "./site";

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
