import type { MetadataRoute } from "next";

import { fetchCategories, fetchSitemap } from "./blog/_lib/api";
import type { BlogCategory } from "./blog/_lib/api";
import { buildBlogSitemap, localesToList } from "./blog/_lib/sitemap";

// Read at request time. A cached sitemap is a sitemap that stops mentioning
// posts as they go live on the publishing schedule (spec §15).
export const dynamic = "force-dynamic";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  // A dead API must not take the sitemap down with it. Serving the static
  // pages beats serving a 500: Google retries a thin sitemap, but an erroring
  // one gets flagged in Search Console and re-fetched far less often.
  const posts = await fetchSitemap().catch(() => []);
  const locales = localesToList(posts);
  const categoriesByLocale: Record<string, BlogCategory[]> = {};
  await Promise.all(
    locales.map(async (locale) => {
      categoriesByLocale[locale] = await fetchCategories(locale).catch(() => []);
    }),
  );
  return buildBlogSitemap({ posts, categoriesByLocale });
}
