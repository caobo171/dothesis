/**
 * Palette for the generated Open Graph card (spec §10).
 *
 * Keyed by category so a reader scrolling a feed of shared links can tell an
 * SPSS post from a thesis-writing post at thumbnail size, before any text is
 * legible. The hues are the landing page's indigo pulled around the wheel far
 * enough to separate nine categories while staying in the same family — nine
 * unrelated colours would read as nine different websites.
 *
 * Kept out of `opengraph-image.tsx` so it can be unit-tested: that file is a
 * Next file-convention route and exporting anything else from it is asking for
 * trouble.
 */
export type OgPalette = { from: string; to: string; accent: string };

const DEFAULT_PALETTE: OgPalette = { from: "#1c2eff", to: "#0a1ee0", accent: "#c7ceff" };

const PALETTES: Record<string, OgPalette> = {
  spss: { from: "#1c2eff", to: "#0a1ee0", accent: "#c7ceff" },
  "thong-ke": { from: "#0f766e", to: "#0b5a54", accent: "#a7ede6" },
  "khao-sat": { from: "#b45309", to: "#8e4207", accent: "#fbdba7" },
  "nghien-cuu-khoa-hoc": { from: "#4338ca", to: "#2f2795", accent: "#cbc7ff" },
  "khoa-luan-tot-nghiep": { from: "#9d174d", to: "#79103c", accent: "#fbc3da" },
  smartpls: { from: "#0369a1", to: "#02507a", accent: "#b0e0fb" },
  "phan-tich-du-lieu": { from: "#4a6b4f", to: "#39533d", accent: "#cfe3d2" },
  "luan-van-thac-si": { from: "#6d28d9", to: "#511da3", accent: "#dcc9ff" },
  "mo-hinh-nghien-cuu": { from: "#8e6b2a", to: "#6e5121", accent: "#efdcb4" },
};

/** Never throws and never returns undefined — a missing card is a blank share. */
export function paletteFor(categorySlug: string | null | undefined): OgPalette {
  if (!categorySlug) return DEFAULT_PALETTE;
  return PALETTES[categorySlug] ?? DEFAULT_PALETTE;
}

/**
 * Font size for the card's headline.
 *
 * satori does not reflow-and-shrink, so a 90-character Vietnamese title at a
 * fixed size runs off the canvas. Stepping the size by title length keeps the
 * longest realistic title inside four lines.
 */
export function titleFontSize(title: string): number {
  if (title.length > 90) return 46;
  if (title.length > 60) return 54;
  if (title.length > 38) return 62;
  return 70;
}
