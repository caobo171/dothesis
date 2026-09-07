import Link from "next/link";

import type { CompactPost } from "../_lib/api";
import { formatDate, formatReadingTime } from "../_lib/format";
import { categoryPath, ogImagePath, postPath } from "../_lib/site";

/**
 * One card in a listing.
 *
 * The thumbnail is the post's own `opengraph-image` route. There is no image
 * hosting on this project yet (spec §2), and the generated card at least
 * carries the title and the category — a stock photo of a laptop would carry
 * nothing and cost a request to a CDN we do not run.
 */
export function PostCard({ post }: { post: CompactPost }) {
  const href = postPath(post.locale, post.slug);
  const date = formatDate(post.published_at, post.locale);
  const read = formatReadingTime(post.reading_time, post.locale);
  return (
    <article className="blog-card">
      <Link href={href} className="blog-card__thumb" aria-hidden="true" tabIndex={-1}>
        <img
          src={post.image_url || ogImagePath(post.locale, post.slug)}
          alt=""
          width={1200}
          height={630}
          loading="lazy"
          decoding="async"
        />
      </Link>
      <h2 className="blog-card__title">
        <Link href={href}>{post.title}</Link>
      </h2>
      {post.excerpt && <p className="blog-card__excerpt">{post.excerpt}</p>}
      <div className="blog-meta">
        {post.category && (
          <>
            <Link href={categoryPath(post.locale, post.category.slug)}>
              {post.category.display_name}
            </Link>
            <span className="blog-meta__sep">·</span>
          </>
        )}
        {date && <time dateTime={post.published_at ?? undefined}>{date}</time>}
        {date && read && <span className="blog-meta__sep">·</span>}
        {read && <span>{read}</span>}
      </div>
    </article>
  );
}
