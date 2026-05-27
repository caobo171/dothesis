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
  async redirects() {
    return [
      { source: "/wizard", destination: "/chat", permanent: true },
    ];
  },
};

export default nextConfig;
