import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { isLocale } from "../../../../lib/i18n/locale";
import { BlogShell } from "../../../_components/BlogShell";
import { CategoryChips } from "../../../_components/CategoryChips";
import { Markdown } from "../../../_components/Markdown";
import { Pagination } from "../../../_components/Pagination";
import { PAGE_SIZE, fetchCategory, fetchPosts } from "../../../_lib/api";
import { formatDate, formatReadingTime } from "../../../_lib/format";
import { plainText, splitLead } from "../../../_lib/markdown";
import { absoluteUrl, categoryPath, postPath } from "../../../_lib/site";

export const dynamic = "force-dynamic";

type Params = { locale: string; category: string };
type Search = { page?: string | string[] };

/** Posts per category page. Higher than the card grid: this is a link hub, and
 *  its whole job is to put as many crawlable anchors on one page as it can. */
const CATEGORY_PAGE_SIZE = 30;

const COPY: Record<
  string,
  { empty: string; siblings: string; all: string; about: string; count: (n: number) => string }
> = {
  vi: {
    empty: "Chưa có bài viết trong chủ đề này.",
    siblings: "Chủ đề khác",
    all: "Tất cả bài viết",
    about: "Về chuyên mục này",
    count: (n) => `${n} bài viết`,
  },
  en: {
    empty: "No posts in this topic yet.",
    siblings: "Other topics",
    all: "All posts",
    about: "About this topic",
    count: (n) => `${n} ${n === 1 ? "post" : "posts"}`,
  },
};

function readPage(search: Search | undefined): number {
  const raw = Array.isArray(search?.page) ? search?.page[0] : search?.page;
  const n = Number.parseInt(raw ?? "1", 10);
  return Number.isFinite(n) && n > 0 ? n : 1;
}

export async function generateMetadata({
  params,
}: {
  params: Promise<Params>;
}): Promise<Metadata> {
  const { locale, category } = await params;
  if (!isLocale(locale)) return {};
  const { category: cat } = await fetchCategory(locale, category);
  if (!cat) return {};
  const canonical = absoluteUrl(categoryPath(locale, cat.slug));
  const title = `${cat.display_name} | DoThesis`;
  // The intro is hand-written per category (spec §6) and its first paragraph
  // doubles as the meta description — which is exactly why the page can set
  // that paragraph as its lead. Both read it through `splitLead` so the two
  // can never drift; an intro that opens with a heading has no lead, and the
  // whole intro is summarised instead.
  const { lead } = splitLead(cat.intro_md ?? "");
  const description = plainText(lead || cat.intro_md || "").slice(0, 300);
  return {
    // metadataBase so any relative URL Next resolves here lands on the public
    // origin rather than on the request host, which behind a proxy is internal.
    metadataBase: new URL(absoluteUrl("/")),
    title,
    description,
    alternates: { canonical },
    openGraph: { type: "website", title, description, url: canonical },
    twitter: { card: "summary_large_image", title, description },
  };
}

export default async function BlogCategoryPage({
  params,
  searchParams,
}: {
  params: Promise<Params>;
  searchParams: Promise<Search>;
}) {
  const { locale, category } = await params;
  if (!isLocale(locale)) notFound();
  const page = readPage(await searchParams);
  const copy = COPY[locale] ?? COPY.en;

  const { category: cat, siblings } = await fetchCategory(locale, category);
  // A category that is not in the taxonomy is a 404, not an empty page: the
  // nine slugs are fixed (spec §6) and anything else is a typo or a probe.
  if (!cat) notFound();

  const list = await fetchPosts({
    locale,
    page,
    category: cat.slug,
    pageSize: CATEGORY_PAGE_SIZE,
  });

  // Every word of the intro still ships; only the order changes. The opening
  // paragraph orients the reader above the list, and the remaining four wait
  // under their own heading below it, so the posts — the thing the reader came
  // for — are on the first screen instead of five paragraphs down.
  const { lead, rest } = splitLead(cat.intro_md ?? "");

  return (
    <BlogShell>
      <header className="blog-hero">
        <div className="lp-wrap">
          {/* Same measure as the body below. The hero used to run the full
              1160px wrap while the posts sat in a centred 720px column, so the
              H1 and the text under it did not share a left edge. */}
          <div className="blog-measure">
            <h1 className="blog-hero__title">{cat.display_name}</h1>
            {/* `list.total` rather than `cat.post_count`: this is the number of
                posts the pager below actually walks through, and it is the
                count sitting directly above that list. */}
            {list.total > 0 && <p className="blog-hero__count">{copy.count(list.total)}</p>}
            {lead && (
              <div className="blog-lead">
                <Markdown>{lead}</Markdown>
              </div>
            )}
            <CategoryChips categories={[cat, ...siblings]} locale={locale} active={cat.slug} />
          </div>
        </div>
      </header>
      <div className="lp-wrap">
        <div className="blog-measure">
          {list.posts.length === 0 ? (
            <p className="blog-empty">{copy.empty}</p>
          ) : (
            <ul className="blog-rows">
              {list.posts.map((post) => {
                const date = formatDate(post.published_at, post.locale);
                const read = formatReadingTime(post.reading_time, post.locale);
                return (
                  <li key={post.slug} className="blog-row">
                    <h2 className="blog-row__title">
                      <Link href={postPath(post.locale, post.slug)}>{post.title}</Link>
                    </h2>
                    {post.excerpt && <p className="blog-row__excerpt">{post.excerpt}</p>}
                    {(date || read) && (
                      <div className="blog-meta">
                        {date && (
                          <time dateTime={post.published_at ?? undefined}>{date}</time>
                        )}
                        {date && read && <span className="blog-meta__sep">·</span>}
                        {read && <span>{read}</span>}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}

          <Pagination
            page={list.page || page}
            total={list.total}
            pageSize={list.page_size || PAGE_SIZE}
            locale={locale}
            hrefFor={(p) =>
              p > 1 ? `${categoryPath(locale, cat.slug)}?page=${p}` : categoryPath(locale, cat.slug)
            }
          />

          {rest && (
            <section className="blog-related">
              <h2 className="blog-section-title">{copy.about}</h2>
              <div className="blog-about">
                <Markdown>{rest}</Markdown>
              </div>
            </section>
          )}

          {siblings.length > 0 && (
            <section className="blog-siblings">
              <h2 className="blog-section-title">{copy.siblings}</h2>
              {/* Chips, not a stacked list of links. `active` is this page's own
                  slug, which no sibling carries, so nothing here is marked
                  current and the "all posts" chip stays a plain link. */}
              <CategoryChips categories={siblings} locale={locale} active={cat.slug} />
            </section>
          )}
        </div>
      </div>
    </BlogShell>
  );
}
