import Link from "next/link";

import type { BlogCategory } from "../_lib/api";
import { blogPath, categoryPath } from "../_lib/site";

const ALL: Record<string, string> = { vi: "Tất cả", en: "All" };

/**
 * The category rail on the listing and the category pages.
 *
 * Plain anchors to real routes rather than a client-side filter: these nine
 * pages are the blog's internal link graph, and a filter that never changes
 * the URL gives a crawler nothing to follow.
 */
export function CategoryChips({
  categories,
  locale,
  active,
}: {
  categories: BlogCategory[];
  locale: string;
  active?: string;
}) {
  if (!categories.length) return null;
  return (
    <div className="blog-chips">
      <Link
        href={blogPath(locale)}
        className="blog-chip"
        aria-current={active ? undefined : "page"}
      >
        {ALL[locale] ?? ALL.en}
      </Link>
      {categories.map((c) => (
        <Link
          key={c.slug}
          href={categoryPath(locale, c.slug)}
          className="blog-chip"
          aria-current={active === c.slug ? "page" : undefined}
        >
          {c.display_name}
          {c.post_count > 0 && <span className="blog-chip__count">{c.post_count}</span>}
        </Link>
      ))}
    </div>
  );
}
