import type { Heading } from "../_lib/markdown";

const TITLE: Record<string, string> = {
  vi: "Nội dung bài viết",
  en: "In this article",
};

/**
 * Auto-generated contents from the body's H2s (spec §10).
 *
 * Hidden below two entries: a "contents" box listing one section is furniture,
 * not navigation, and it pushes the first paragraph below the fold for nothing.
 *
 * The hrefs come from the same slugger the renderer uses, so they cannot drift
 * from the ids in the body — see `_lib/markdown.ts`.
 */
export function ContentsBox({
  headings,
  locale,
}: {
  headings: Heading[];
  locale: string;
}) {
  if (headings.length < 2) return null;
  return (
    <nav className="blog-toc" aria-label={TITLE[locale] ?? TITLE.en}>
      <div className="blog-toc__title">{TITLE[locale] ?? TITLE.en}</div>
      <ol>
        {headings.map((h) => (
          <li key={h.id}>
            <a href={`#${h.id}`}>{h.text}</a>
          </li>
        ))}
      </ol>
    </nav>
  );
}
