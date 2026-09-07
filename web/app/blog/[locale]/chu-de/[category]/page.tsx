import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { isLocale } from "../../../../lib/i18n/locale";
import { BlogShell } from "../../../_components/BlogShell";
import { CategoryChips } from "../../../_components/CategoryChips";
import { Markdown } from "../../../_components/Markdown";
import { Pagination } from "../../../_components/Pagination";
import { PAGE_SIZE, fetchCategory, fetchPosts } from "../../../_lib/api";
import { formatDate } from "../../../_lib/format";
import { absoluteUrl, categoryPath, postPath } from "../../../_lib/site";

export const dynamic = "force-dynamic";

type Params = { locale: string; category: string };
type Search = { page?: string | string[] };

/** Posts per category page. Higher than the card grid: this is a link hub, and
 *  its whole job is to put as many crawlable anchors on one page as it can. */
const CATEGORY_PAGE_SIZE = 30;

const COPY: Record<string, { empty: string; siblings: string; all: string }> = {
  vi: { empty: "Chưa có bài viết trong chủ đề này.", siblings: "Chủ đề khác", all: "Tất cả bài viết" },
  en: { empty: "No posts in this topic yet.", siblings: "Other topics", all: "All posts" },
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
  // The intro is hand-written per category (spec §6) and doubles as the meta
  // description; its first sentence is written to stand alone for that reason.
  const description = cat.intro_md.replace(/[#*_`>\[\]]/g, "").split(/\n+/)[0]?.slice(0, 300) ?? "";
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

  return (
    <BlogShell>
      <header className="blog-hero">
        <div className="lp-wrap">
          <h1 className="blog-hero__title">{cat.display_name}</h1>
          <CategoryChips categories={[cat, ...siblings]} locale={locale} active={cat.slug} />
        </div>
      </header>
      <div className="lp-wrap">
        <div className="blog-measure">
          {cat.intro_md && <Markdown>{cat.intro_md}</Markdown>}

          {list.posts.length === 0 ? (
            <p className="blog-empty">{copy.empty}</p>
          ) : (
            <ul className="blog-linklist" style={{ marginTop: 36 }}>
              {list.posts.map((post) => (
                <li key={post.slug}>
                  <Link href={postPath(post.locale, post.slug)}>{post.title}</Link>
                  <div className="blog-meta">
                    {post.published_at && (
                      <time dateTime={post.published_at}>
                        {formatDate(post.published_at, post.locale)}
                      </time>
                    )}
                  </div>
                </li>
              ))}
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

          {siblings.length > 0 && (
            <section className="blog-related">
              <h2 className="blog-section-title">{copy.siblings}</h2>
              <ul className="blog-linklist">
                {siblings.map((s) => (
                  <li key={s.slug}>
                    <Link href={categoryPath(locale, s.slug)}>{s.display_name}</Link>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>
    </BlogShell>
  );
}
