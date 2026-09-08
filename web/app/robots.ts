import { headers } from "next/headers";
import type { MetadataRoute } from "next";

import { SITE_ORIGIN } from "./blog/_lib/site";
import { hostFromHeader, isAppHost } from "./lib/hosts";

/**
 * robots.txt (spec §10), answered per hostname.
 *
 * One deployment serves the marketing apex and the app subdomain, so a single
 * static robots.txt would be wrong on one of them. On the app host the whole
 * origin is closed: every path there is auth-gated and 307s a signed-out
 * crawler to /login, and the public content it can reach is a duplicate of the
 * marketing host's copy. On the marketing host `/chat`, `/admin` and `/api`
 * stay disallowed for the same auth-gate reason, and `/blog` and `/landing`
 * are named explicitly so the intent is readable to whoever edits this next.
 *
 * Reading a header makes this route dynamic. That is the point: the answer
 * depends on who is asking, and it is two lines of text.
 */
export default async function robots(): Promise<MetadataRoute.Robots> {
  const host = hostFromHeader((await headers()).get("host"));

  if (isAppHost(host)) {
    return { rules: [{ userAgent: "*", disallow: "/" }] };
  }

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
