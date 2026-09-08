import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { isLocale } from "../../lib/i18n/locale";
import { BlogShell } from "../_components/BlogShell";
import { CategoryChips } from "../_components/CategoryChips";
import { Pagination } from "../_components/Pagination";
import { PostCard } from "../_components/PostCard";
import { PAGE_SIZE, fetchCategories, fetchPosts } from "../_lib/api";
import { alternateLanguages, otherLocale } from "../_lib/hreflang";
import { absoluteUrl, listingPath } from "../_lib/site";

// The listing reads `?page=` and fetches with no-store, so there is nothing to
// prerender. Declared rather than inferred so a `next build` can never try to
// reach the API from the build machine.
export const dynamic = "force-dynamic";

type Params = { locale: string };
type Search = { page?: string | string[] };

const COPY: Record<
  string,
  { title: string; sub: string; empty: string; metaTitle: string; pageSuffix: (n: number) => string }
> = {
  vi: {
    title: "Blog DoThesis",
    sub: "Hướng dẫn SPSS, SmartPLS, thang đo và cách viết luận văn định lượng — viết cho sinh viên đang làm khóa luận, không phải cho giảng viên đọc lại.",
    empty: "Chưa có bài viết nào.",
    metaTitle: "Blog — SPSS, SmartPLS và luận văn định lượng | DoThesis",
    pageSuffix: (n) => ` — trang ${n}`,
  },
  en: {
    title: "DoThesis blog",
    sub: "Guides to SPSS, SmartPLS, measurement scales and writing a quantitative thesis.",
    empty: "No posts yet.",
    metaTitle: "Blog — SPSS, SmartPLS and quantitative theses | DoThesis",
    pageSuffix: (n) => ` — page ${n}`,
  },
};

/** `?page=2` from a URL that could legitimately repeat the parameter. */
function readPage(search: Search | undefined): number {
  const raw = Array.isArray(search?.page) ? search?.page[0] : search?.page;
  const n = Number.parseInt(raw ?? "1", 10);
  return Number.isFinite(n) && n > 0 ? n : 1;
}

export async function generateMetadata({
  params,
  searchParams,
}: {
  params: Promise<Params>;
  searchParams: Promise<Search>;
}): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocale(locale)) return {};
  const page = readPage(await searchParams);
  const copy = COPY[locale] ?? COPY.en;
  // Every paginated page canonicalises to ITSELF. Pointing page 2 at page 1
  // would tell Google the posts only reachable from page 2 are duplicates of
  // a page that does not list them, and they drop out of the index.
  const canonical = absoluteUrl(listingPath(locale, page));
  const title = page > 1 ? `${copy.metaTitle}${copy.pageSuffix(page)}` : copy.metaTitle;

  // The other edition's listing is only a real alternate if it has posts on
  // THIS page number. `/blog/en` exists as a route from day one and answers 200
  // with "No posts yet", and page 4 of an edition with two pages is an empty
  // list — pointing hreflang at either would annotate a page with no content,
  // which Google reads as a broken cluster rather than as a translation.
  const other = otherLocale(locale);
  const otherHasThisPage = await fetchPosts({ locale: other, page, pageSize: PAGE_SIZE })
    .then((list) => list.posts.length > 0)
    .catch(() => false);

  return {
    // metadataBase so any relative URL Next resolves here lands on the public
    // origin rather than on the request host, which behind a proxy is internal.
    metadataBase: new URL(absoluteUrl("/")),
    title,
    description: copy.sub,
    alternates: {
      canonical,
      languages: alternateLanguages({
        [locale]: canonical,
        ...(otherHasThisPage ? { [other]: absoluteUrl(listingPath(other, page)) } : {}),
      }),
    },
    openGraph: { type: "website", title, description: copy.sub, url: canonical },
    twitter: { card: "summary_large_image", title, description: copy.sub },
  };
}

export default async function BlogListingPage({
  params,
  searchParams,
}: {
  params: Promise<Params>;
  searchParams: Promise<Search>;
}) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  const page = readPage(await searchParams);
  const copy = COPY[locale] ?? COPY.en;

  const [list, categories] = await Promise.all([
    fetchPosts({ locale, page }),
    fetchCategories(locale),
  ]);

  return (
    <BlogShell>
      <header className="blog-hero">
        <div className="lp-wrap">
          <h1 className="blog-hero__title">{copy.title}</h1>
          <p className="blog-hero__sub">{copy.sub}</p>
          <CategoryChips categories={categories} locale={locale} />
        </div>
      </header>
      <div className="lp-wrap">
        {list.posts.length === 0 ? (
          <p className="blog-empty">{copy.empty}</p>
        ) : (
          <div className="blog-grid">
            {list.posts.map((post) => (
              <PostCard key={post.slug} post={post} />
            ))}
          </div>
        )}
        <Pagination
          page={list.page || page}
          total={list.total}
          pageSize={list.page_size || PAGE_SIZE}
          locale={locale}
          hrefFor={(p) => listingPath(locale, p)}
        />
      </div>
    </BlogShell>
  );
}
