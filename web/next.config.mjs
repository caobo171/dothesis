/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Legacy wizard surface retired 2026-05-27 — chat UI (SP7) is the new entry point.
  // Permanent redirect so bookmarks and external links still land somewhere useful.
  async redirects() {
    return [
      { source: "/wizard", destination: "/chat", permanent: true },
    ];
  },
};

export default nextConfig;
