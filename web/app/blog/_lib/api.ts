/**
 * Typed server-side readers for the public blog API (spec §8).
 *
 * Every call is a POST with the lookup parameters in the body — the repo is
 * POST-only (CLAUDE.md) and these routes are no exception even though they are
 * pure reads. `auth: false` because the blog is the one surface with no user:
 * injecting a token would be both pointless and, on the server, impossible
 * (the token lives in the reader's localStorage).
 *
 * `cache: "no-store"` on every fetch: a published post can be corrected, and a
 * schedule can flip a post live at any minute of the day. Serving a cached copy
 * of a page a crawler is being pointed at by a freshly-regenerated sitemap is
 * the one failure mode worth paying a request for.
 */
import { apiFetch } from "@/app/lib/api";

/** The category shape a post carries inline — just enough to render a chip. */
export type BlogCategoryRef = { slug: string; display_name: string };

/** A post as it appears in a list: everything but the body. */
export type CompactPost = {
  slug: string;
  locale: string;
  title: string;
  excerpt: string;
  image_url: string | null;
  category: BlogCategoryRef | null;
  tags: string[];
  published_at: string | null;
  updated_at?: string | null;
  reading_time: number;
  // Only the full serializer emits these; a listing card never shows them.
  focus_keyword?: string | null;
  views?: number;
};

/** A post as it appears on its own page. */
export type FullPost = CompactPost & {
  body: string;
  meta_title: string;
  meta_description: string;
  canonical_url: string | null;
  updated_at: string | null;
  focus_keyword: string | null;
  secondary_keywords: string[];
  archetype: string | null;
};

export type BlogCategory = {
  slug: string;
  name: string;
  display_name: string;
  intro_md: string;
  post_count: number;
};

export type PostList = {
  posts: CompactPost[];
  total: number;
  page: number;
  page_size: number;
};

/** Where the same article lives in another language. */
export type TranslationRef = { locale: string; slug: string };

export type PostDetail = {
  post: FullPost;
  related: CompactPost[];
  category: BlogCategory | null;
  /** Other visible editions of this article, for hreflang. Empty when none. */
  translations: TranslationRef[];
};

export type SitemapEntry = { locale: string; slug: string; updated_at: string | null };

/** Cards per listing page. Also the page size the pager and the API agree on. */
export const PAGE_SIZE = 12;

async function post<T>(path: string, body: Record<string, unknown>): Promise<T> {
  return (await apiFetch(path, {
    method: "POST",
    auth: false,
    body,
    cache: "no-store",
  })) as T;
}

/** True for the one error a public page should render as "nothing here". */
function isNotFound(err: unknown): boolean {
  return typeof err === "object" && err !== null && (err as { status?: number }).status === 404;
}

export async function fetchPosts(params: {
  locale: string;
  page?: number;
  pageSize?: number;
  category?: string;
  q?: string;
}): Promise<PostList> {
  const body: Record<string, unknown> = {
    locale: params.locale,
    page: params.page && params.page > 0 ? params.page : 1,
    page_size: params.pageSize ?? PAGE_SIZE,
  };
  // Absent filters are omitted rather than sent as null: the API treats a
  // present `category` as a filter, and an explicit null would make "all
  // posts" indistinguishable from "posts with no category".
  if (params.category) body.category = params.category;
  if (params.q) body.q = params.q;

  const res = await post<Partial<PostList>>("/blog/list", body);
  return {
    posts: res.posts ?? [],
    total: res.total ?? 0,
    page: res.page ?? 1,
    page_size: res.page_size ?? PAGE_SIZE,
  };
}

/**
 * One post, or null when there is no such slug.
 *
 * Only a 404 becomes null. A 500 or a dead API is deliberately allowed to
 * throw: turning an outage into `notFound()` would serve a real 404 for a URL
 * that is in the sitemap, and Google drops those from the index far faster
 * than it retries a 500.
 */
export async function fetchPost(locale: string, slug: string): Promise<PostDetail | null> {
  try {
    const res = await post<Record<string, unknown>>("/blog/get", { locale, slug });
    return normalizePostDetail(res);
  } catch (err) {
    if (isNotFound(err)) return null;
    throw err;
  }
}

/**
 * Accept both shapes `/blog/get` has been written to.
 *
 * The design (spec §8) specifies `{post, related, category}`; the router that
 * shipped returns the full post at the top level with `related` nested inside
 * it and the category under `post.category`. Normalising here rather than
 * picking a side means the blog keeps rendering whichever way that route is
 * settled, and the pages above never learn about it.
 */
export function normalizePostDetail(res: Record<string, unknown> | null): PostDetail | null {
  if (!res) return null;
  const wrapped = res.post as FullPost | undefined;
  const inner = wrapped ?? (res as unknown as FullPost);
  if (!inner || typeof inner.slug !== "string") return null;
  const related = (res.related as CompactPost[] | undefined)
    ?? ((inner as unknown as { related?: CompactPost[] }).related ?? []);
  const category = (res.category as BlogCategory | null | undefined)
    ?? (inner.category as BlogCategory | null | undefined)
    ?? null;
  // `/blog/get` returns these off a shared `translation_key`; an older API that
  // does not know the field simply sends none, and the page then declares no
  // hreflang rather than guessing at one.
  const raw = (res.translations as TranslationRef[] | undefined)
    ?? ((inner as unknown as { translations?: TranslationRef[] }).translations ?? []);
  const translations = raw.filter(
    (t) => t && typeof t.locale === "string" && typeof t.slug === "string");
  return { post: inner, related, category, translations };
}

export async function fetchCategories(locale: string): Promise<BlogCategory[]> {
  const res = await post<{ categories?: BlogCategory[] }>("/blog/categories", { locale });
  return res.categories ?? [];
}

/** One category by slug, or null — the API has no single-category read. */
export async function fetchCategory(
  locale: string,
  slug: string,
): Promise<{ category: BlogCategory | null; siblings: BlogCategory[] }> {
  const categories = await fetchCategories(locale);
  return {
    category: categories.find((c) => c.slug === slug) ?? null,
    siblings: categories.filter((c) => c.slug !== slug),
  };
}

/**
 * The sitemap feed. Same story as `/blog/get`: the design says
 * `{posts: [...]}` and the shipped router returns the bare array, so both are
 * accepted rather than betting the sitemap on which one lands.
 */
export async function fetchSitemap(locale?: string): Promise<SitemapEntry[]> {
  const res = await post<SitemapEntry[] | { posts?: SitemapEntry[] }>(
    "/blog/sitemap",
    locale ? { locale } : {},
  );
  if (Array.isArray(res)) return res;
  return res?.posts ?? [];
}
