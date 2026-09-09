/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Proxy /api/v1/* to the FastAPI backend. The chat surface uses relative
  // URLs (fetch("/api/v1/...")) so the browser hits the Next.js dev server
  // and we forward to the API service. Default port matches `dev.sh`'s
  // uvicorn boot (7100); override in dev with NEXT_PUBLIC_API_PROXY_TARGET.
  async rewrites() {
    const target = process.env.NEXT_PUBLIC_API_PROXY_TARGET || "http://localhost:7100";
    return [
      { source: "/api/v1/:path*", destination: `${target}/api/v1/:path*` },
    ];
  },
  // Legacy wizard surface retired 2026-05-27 — chat UI (SP7) is the new entry point.
  // Permanent redirect so bookmarks and external links still land somewhere useful.
  //
  // Retired blog slugs live here too. A merged post's URL has to keep resolving:
  // the body links in its neighbours were written before the merge and are
  // already in the database, and the sitemap that named it has been crawled.
  // `permanent: true` is a 308, which Google consolidates into the destination
  // exactly as it does a 301 — that consolidation is the point of merging two
  // posts, so the redirect has to be permanent rather than a 307.
  //
  // These are baked at build time, so a retired slug needs a web build BEFORE
  // its row leaves the database. The other way round is a 404 on a URL that
  // dozens of published posts link to. `app.blog.cli retire` prints the line.
  async redirects() {
    return [
      { source: "/wizard", destination: "/chat", permanent: true },
      // Merged 2026-09-09: "outliers" was the plural spelling of "outlier",
      // same 6,600-volume keyword and the same title after the plural. The
      // singular kept the page; see api/app/blog/similarity.py for the guard
      // that now refuses the pair.
      { source: "/blog/vi/outliers", destination: "/blog/vi/outlier", permanent: true },
    ];
  },
};

export default nextConfig;
