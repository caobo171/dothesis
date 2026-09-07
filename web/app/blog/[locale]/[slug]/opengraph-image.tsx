import { ImageResponse } from "next/og";

import { fetchPost } from "../../_lib/api";
import { paletteFor, titleFontSize } from "../../_lib/og";

export const alt = "DoThesis";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/**
 * The share card for a post, and the thumbnail its listing card uses.
 *
 * Generated rather than uploaded: this project has no public image hosting
 * (spec §2), and a thousand posts would otherwise share one stock image —
 * which is worse than no image, because every share of every article would
 * look like the same article.
 *
 * Text only, no logo file: satori would have to fetch the PNG over HTTP on
 * every render, and a failed fetch takes the whole card down with it.
 *
 * No `fontFamily` and no font loading either. next/og bundles Geist Regular as
 * its default, and that face does cover Vietnamese (checked: đ U+0111, ế
 * U+1EBF, ạ U+1EA1 are all in its cmap) — naming a family satori has not been
 * given would only send it back to the same default by a longer route.
 */
export default async function Image({
  params,
}: {
  params: Promise<{ locale: string; slug: string }>;
}) {
  const { locale, slug } = await params;
  const data = await fetchPost(locale, slug).catch(() => null);
  const post = data?.post;
  const title = post?.title ?? "DoThesis";
  const category = data?.category?.display_name ?? post?.category?.display_name ?? "DoThesis";
  const palette = paletteFor(data?.category?.slug ?? post?.category?.slug ?? null);

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
          background: `linear-gradient(135deg, ${palette.from} 0%, ${palette.to} 100%)`,
          color: "#ffffff",
        }}
      >
        <div
          style={{
            display: "flex",
            fontSize: 26,
            letterSpacing: 4,
            textTransform: "uppercase",
            color: palette.accent,
          }}
        >
          {category}
        </div>
        <div
          style={{
            display: "flex",
            fontSize: titleFontSize(title),
            lineHeight: 1.15,
            fontWeight: 700,
            // satori has no ellipsis: a title longer than the card is cut here
            // rather than overflowing off the canvas.
            maxHeight: 340,
            overflow: "hidden",
          }}
        >
          {title}
        </div>
        <div style={{ display: "flex", alignItems: "center", fontSize: 30, fontWeight: 700 }}>
          DoThesis
        </div>
      </div>
    ),
    size,
  );
}
