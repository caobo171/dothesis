"use client";

import Link from "next/link";

import "../../../landing/landing.css";
import "../../../blog/blog.css";

import { ContentsBox } from "@/app/blog/_components/ContentsBox";
import { CtaBlock } from "@/app/blog/_components/CtaBlock";
import { Markdown } from "@/app/blog/_components/Markdown";
import { formatDate, formatReadingTime } from "@/app/blog/_lib/format";
import { readingTime, tableOfContents } from "@/app/blog/_lib/markdown";

/**
 * What the post will actually look like, rendered by the code that will render
 * it.
 *
 * Deliberately NOT a markdown pane styled to resemble the article. Every blog
 * rule in blog.css is scoped under `.lp-root`, and the body is run through the
 * same remark/rehype stack the public page uses, so a preview that reproduced
 * the look by hand would drift the first time either changed and would be
 * wrong in exactly the way that matters — the operator would trust it.
 *
 * landing.css rides along because blog.css depends on its tokens and the
 * `.lp-root` scope: BlogShell imports the pair together for this reason, and
 * this is the second place that scope is opened.
 *
 * What is missing next to the real page, and why: the marketing Nav/Footer
 * (BlogShell), JSON-LD, and the related-posts list. None of them render the
 * author's copy — they are chrome and machine-readable metadata — and pulling
 * BlogShell in would drag the landing header into an admin screen.
 */
export function PostPreview({
  title,
  body,
  locale,
  imageUrl,
  categoryName,
  publishedAt,
}: {
  title: string;
  body: string;
  locale: string;
  imageUrl?: string | null;
  categoryName?: string | null;
  publishedAt?: string | null;
}) {
  const headings = tableOfContents(body);
  // The stored reading_time is written at save; before the first save there is
  // nothing to show, so it is computed from the draft in hand.
  const read = formatReadingTime(readingTime(body), locale);
  const date = publishedAt ? formatDate(publishedAt, locale) : null;

  return (
    <div className="lp-root">
      <div className="lp-wrap">
        <article className="blog-article blog-measure">
          {imageUrl && (
            <img
              className="blog-article__hero"
              src={imageUrl}
              alt=""
              width={1200}
              height={800}
              decoding="async"
            />
          )}

          <h1 className="blog-article__title">{title || "Untitled"}</h1>

          <div className="blog-meta" style={{ marginTop: 16 }}>
            {categoryName && (
              <>
                <span>{categoryName}</span>
                <span className="blog-meta__sep">·</span>
              </>
            )}
            {date && <time dateTime={publishedAt ?? undefined}>{date}</time>}
            {date && read && <span className="blog-meta__sep">·</span>}
            {read && <span>{read}</span>}
          </div>

          <ContentsBox headings={headings} locale={locale} />

          <Markdown>{body}</Markdown>

          <CtaBlock locale={locale} />
        </article>
      </div>
    </div>
  );
}

/** A reader's-eye link to the live page, for a post that has one. */
export function LivePostLink({ locale, slug }: { locale: string; slug: string }) {
  return (
    <Link
      href={`/blog/${locale}/${slug}`}
      target="_blank"
      className="text-sm font-semibold text-primary-700 hover:text-primary-800"
    >
      Open live page ↗
    </Link>
  );
}
