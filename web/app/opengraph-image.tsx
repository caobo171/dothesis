import { ImageResponse } from "next/og";

export const alt = "DoThesis — from a topic idea to a submitted thesis";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/**
 * The site-wide share card: what Facebook, Zalo, LinkedIn, X and iMessage show
 * for dothesis.com and for every page that does not generate its own. Blog
 * posts do generate their own (app/blog/[locale]/[slug]/opengraph-image.tsx),
 * so this one only ever stands in for the marketing pages and the app shell.
 *
 * Drawn rather than screenshotted. A 1200x630 crop of the landing page is
 * mostly nav bar and a product mock sliced off mid-card, and it goes stale the
 * moment the hero is retouched; the headline is the thing worth showing at
 * thumbnail size. Same satori pipeline, palette and no-font-loading reasoning
 * as the blog card — see that file's header for why no logo file is fetched.
 */
export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "72px 80px",
          background: "linear-gradient(135deg, #1c2eff 0%, #0a1ee0 100%)",
          color: "#ffffff",
        }}
      >
        <div
          style={{
            display: "flex",
            fontSize: 26,
            letterSpacing: 4,
            textTransform: "uppercase",
            color: "#c7ceff",
          }}
        >
          AI Thesis Agent
        </div>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div
            style={{
              display: "flex",
              fontSize: 76,
              lineHeight: 1.12,
              fontWeight: 700,
              letterSpacing: -2,
            }}
          >
            From a topic idea to a submitted thesis.
          </div>
          <div
            style={{
              display: "flex",
              marginTop: 24,
              fontSize: 34,
              color: "#c7ceff",
            }}
          >
            One thread. Real sources. Every citation traced.
          </div>
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            fontSize: 30,
            fontWeight: 700,
          }}
        >
          <div style={{ display: "flex" }}>DoThesis</div>
          <div style={{ display: "flex", fontWeight: 400, color: "#c7ceff" }}>dothesis.com</div>
        </div>
      </div>
    ),
    size,
  );
}
