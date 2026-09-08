/**
 * Which site is this request for?
 *
 * One deployment serves two hostnames: the marketing site on the apex
 * (`dothesis.com`, landing page and blog, all public) and the product on
 * `app.dothesis.com` (everything auth-gated). One build, one systemd service,
 * one set of components, and the split is a routing decision rather than a
 * second deploy to keep in sync.
 *
 * The rules live here as a PURE function rather than inside the middleware so
 * they can be tested without constructing a NextRequest, and so the answer to
 * "what does this host do with this path" has exactly one implementation.
 *
 * With either variable unset the function returns `next` for everything, which
 * is the single-host behaviour `dev.sh` has always had on localhost:3006.
 */

const strip = (value) =>
  (value || "").trim().replace(/^https?:\/\//i, "").replace(/\/+$/, "").toLowerCase();

const stripOrigin = (value) => (value || "").trim().replace(/\/+$/, "");

export const MARKETING_HOST = strip(process.env.NEXT_PUBLIC_MARKETING_HOST);
export const APP_HOST = strip(process.env.NEXT_PUBLIC_APP_HOST);

/** Absolute origins, needed because these redirects cross hostnames. */
export const APP_ORIGIN =
  stripOrigin(process.env.NEXT_PUBLIC_APP_ORIGIN) || (APP_HOST ? `https://${APP_HOST}` : "");
export const MARKETING_ORIGIN =
  stripOrigin(process.env.NEXT_PUBLIC_SITE_ORIGIN) ||
  (MARKETING_HOST ? `https://${MARKETING_HOST}` : "");

/** Both names must be configured, or there is no split to enforce. */
export const SPLIT_ENABLED = Boolean(MARKETING_HOST && APP_HOST);

/** Everything the marketing host serves itself. Anything else belongs to the app. */
const MARKETING_PREFIXES = ["/blog", "/_next", "/sitemap.xml", "/robots.txt"];

/** Public content, wherever it is asked for, has one home: the marketing host. */
const PUBLIC_CONTENT_PREFIXES = ["/blog", "/landing"];

export function hostFromHeader(value) {
  // `Host` carries the port in development and behind some proxies; the port is
  // never part of the identity of the site.
  return strip((value || "").split(",")[0]).split(":")[0];
}

export function isMarketingHost(host) {
  if (!MARKETING_HOST) return false;
  return host === MARKETING_HOST || host === `www.${MARKETING_HOST}`;
}

export function isAppHost(host) {
  return Boolean(APP_HOST) && host === APP_HOST;
}

const under = (pathname, prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`);

/**
 * `{ action: "next" | "rewrite" | "redirect", to?, status? }`.
 *
 * Marketing host:
 *   `/`         renders the landing page, as a rewrite so the canonical URL of
 *               the marketing site is the bare apex rather than `/landing`.
 *   `/landing`  301s to `/`, so the page is not reachable at two URLs. The
 *               rewrite above does not re-enter this function, so there is no
 *               loop between the two rules.
 *   `/blog/…`   served.
 *   anything else is a product route: 308 to the app host, preserving the path
 *               and the method, so an old bookmark still lands in the right place.
 *
 * App host:
 *   `/blog/…` and `/landing` 301 to the marketing host. Public content indexed
 *   under two hostnames is duplicate content, and the crawler picks the winner,
 *   not us.
 */
export function routeForHost(host, pathname) {
  if (!SPLIT_ENABLED) return { action: "next" };

  if (isMarketingHost(host)) {
    if (under(pathname, "/landing")) return { action: "redirect", to: "/", status: 301 };
    if (pathname === "/") return { action: "rewrite", to: "/landing" };
    if (MARKETING_PREFIXES.some((p) => under(pathname, p))) return { action: "next" };
    return { action: "redirect", to: `${APP_ORIGIN}${pathname}`, status: 308, external: true };
  }

  if (isAppHost(host) && PUBLIC_CONTENT_PREFIXES.some((p) => under(pathname, p))) {
    const target = under(pathname, "/landing") ? "/" : pathname;
    return { action: "redirect", to: `${MARKETING_ORIGIN}${target}`, status: 301, external: true };
  }

  return { action: "next" };
}
