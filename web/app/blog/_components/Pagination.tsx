import Link from "next/link";

const LABELS: Record<string, { prev: string; next: string; nav: string }> = {
  vi: { prev: "Trang trước", next: "Trang sau", nav: "Phân trang" },
  en: { prev: "Previous", next: "Next", nav: "Pagination" },
};

/**
 * Windowed page numbers: always the first, the last, and the two either side
 * of the current page, with a gap marker between the runs.
 */
export function pageWindow(page: number, pageCount: number): Array<number | "gap"> {
  const wanted = new Set<number>([1, pageCount, page - 1, page, page + 1]);
  const pages = [...wanted].filter((p) => p >= 1 && p <= pageCount).sort((a, b) => a - b);
  const out: Array<number | "gap"> = [];
  let previous = 0;
  for (const p of pages) {
    if (previous && p - previous > 1) out.push("gap");
    out.push(p);
    previous = p;
  }
  return out;
}

/**
 * Paginator over `?page=`.
 *
 * Every page is a real anchor, not a button: this is the only path a crawler
 * has to posts past the first twelve, and a click handler is invisible to it.
 * `hrefFor` is injected so the listing and a future filtered view can keep
 * their own query strings without this component knowing about them.
 */
export function Pagination({
  page,
  total,
  pageSize,
  locale,
  hrefFor,
}: {
  page: number;
  total: number;
  pageSize: number;
  locale: string;
  hrefFor: (page: number) => string;
}) {
  const pageCount = Math.max(1, Math.ceil(total / Math.max(1, pageSize)));
  if (pageCount < 2) return null;
  const labels = LABELS[locale] ?? LABELS.en;

  return (
    <nav className="blog-pager" aria-label={labels.nav}>
      {page > 1 && (
        <Link href={hrefFor(page - 1)} rel="prev">
          {labels.prev}
        </Link>
      )}
      {pageWindow(page, pageCount).map((entry, i) =>
        entry === "gap" ? (
          <span key={`gap-${i}`} className="blog-pager__gap" aria-hidden="true">
            …
          </span>
        ) : entry === page ? (
          <span key={entry} aria-current="page">
            {entry}
          </span>
        ) : (
          <Link key={entry} href={hrefFor(entry)}>
            {entry}
          </Link>
        ),
      )}
      {page < pageCount && (
        <Link href={hrefFor(page + 1)} rel="next">
          {labels.next}
        </Link>
      )}
    </nav>
  );
}
