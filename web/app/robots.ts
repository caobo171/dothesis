import type { MetadataRoute } from "next";

import { SITE_ORIGIN } from "./blog/_lib/site";

/**
 * robots.txt (spec §10).
 *
 * `/chat`, `/admin` and `/api` are disallowed because they are auth-gated:
 * every one of them 307s a signed-out crawler to /login, so crawling them
 * spends budget to discover the same redirect a few hundred times. `/blog` and
 * `/landing` are named explicitly even though nothing forbids them — an
 * explicit Allow is what makes the intent readable to whoever edits this next.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: ["/blog", "/landing"],
        disallow: ["/chat", "/admin", "/api"],
      },
    ],
    sitemap: `${SITE_ORIGIN}/sitemap.xml`,
    host: SITE_ORIGIN,
  };
}
