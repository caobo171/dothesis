import { render, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, test, vi } from "vitest";

import { server } from "../../tests/setup";

// notFound()/redirect() abort rendering by throwing in Next. Reproduce that
// here so a route that "returns" after calling them would still fail the test.
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
  redirect: (url: string) => {
    throw new Error(`NEXT_REDIRECT:${url}`);
  },
  permanentRedirect: (url: string) => {
    throw new Error(`NEXT_PERMANENT_REDIRECT:${url}`);
  },
}));

import BlogRootPage from "./page";
import BlogListingPage, { generateMetadata as listingMetadata } from "./[locale]/page";
import BlogCategoryPage, {
  generateMetadata as categoryMetadata,
} from "./[locale]/chu-de/[category]/page";
import BlogTopicPage, {
  generateMetadata as topicMetadata,
} from "./[locale]/topic/[category]/page";
import BlogPostPage, { generateMetadata as postMetadata } from "./[locale]/[slug]/page";
import robots from "../robots";
import sitemap from "../sitemap";

// `robots()` answers per hostname, so it reads the request headers. There is no
// request in a unit test: this stands in for one.
vi.mock("next/headers", () => ({
  headers: async () => new Headers({ host: "localhost:3006" }),
}));

const BODY = [
  "## Phân tích EFA",
  "",
  "Nội dung mục một với [liên kết nội bộ](/blog/vi/do-tin-cay).",
  "",
  "| Chỉ số | Ngưỡng |",
  "| --- | --- |",
  "| Alpha | 0.7 |",
  "",
  "## Độ tin cậy",
  "",
  "Nội dung mục hai.",
  "",
  "## Câu hỏi thường gặp",
  "",
  "### Alpha bao nhiêu là đạt?",
  "",
  "Từ 0.7 trở lên.",
  "",
  "### Loại biến nào trước?",
  "",
  "Biến có tương quan biến tổng thấp nhất.",
  "",
].join("\n");

const COMPACT = {
  slug: "cronbach-alpha-la-gi",
  locale: "vi",
  title: "Cronbach's Alpha là gì",
  excerpt: "Một dòng cho trang danh sách.",
  image_url: null,
  category: { slug: "spss", display_name: "SPSS" },
  tags: ["cronbach alpha"],
  published_at: "2026-09-01T09:00:00Z",
  reading_time: 9,
  focus_keyword: "cronbach alpha",
};

const FULL = {
  ...COMPACT,
  body: BODY,
  meta_title: "Cronbach's Alpha là gì | DoThesis",
  meta_description: "Ngưỡng Cronbach's Alpha và cách đọc kết quả trong SPSS.",
  canonical_url: null,
  updated_at: "2026-09-05T09:00:00Z",
  secondary_keywords: ["hệ số cronbach alpha"],
  archetype: "term-la-gi",
};

// Five paragraphs, the shape every live category intro has (spec §6). The
// category page leads with the first and parks the other four below the posts,
// so a single-paragraph fixture would not exercise the split at all.
const INTRO = [
  "SPSS là phần mềm thống kê phổ biến nhất trong luận văn định lượng.",
  "",
  "Chuyên mục này đi theo đúng thứ tự bạn sẽ gặp trong một bài phân tích.",
  "",
  "Bạn sẽ thấy nhiều bài xử lý tình huống hỏng: hệ số tải thấp, ma trận xoay lộn xộn.",
  "",
  "Nếu mô hình có biến trung gian, hãy xem thêm chuyên mục SmartPLS.",
  "",
  "Bắt đầu từ đâu. Đọc bài về làm sạch dữ liệu và mã hóa biến trước.",
].join("\n");

const CATEGORIES = [
  { slug: "spss", name: "SPSS", display_name: "SPSS", intro_md: INTRO, post_count: 20 },
  { slug: "smartpls", name: "SmartPLS", display_name: "SmartPLS", intro_md: "", post_count: 12 },
];

/** True when `a` comes before `b` in document order. */
function precedes(a: Element, b: Element): boolean {
  return Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
}

function stubApi(opts: { posts?: unknown[]; total?: number; detail?: unknown } = {}) {
  server.use(
    http.post("*/api/v1/blog/list", () =>
      HttpResponse.json({
        posts: opts.posts ?? [COMPACT],
        total: opts.total ?? 1,
        page: 1,
        page_size: 12,
      }),
    ),
    http.post("*/api/v1/blog/categories", () => HttpResponse.json({ categories: CATEGORIES })),
    http.post("*/api/v1/blog/get", () =>
      HttpResponse.json(
        opts.detail ?? { post: FULL, related: [COMPACT], category: CATEGORIES[0] },
      ),
    ),
  );
}

describe("/blog", () => {
  test("redirects to the Vietnamese listing", () => {
    expect(() => BlogRootPage()).toThrow("NEXT_REDIRECT:/blog/vi");
  });
});

describe("/blog/[locale]", () => {
  test("renders the hero, the category chips and one card per post", async () => {
    stubApi();
    const { container } = render(
      await BlogListingPage({
        params: Promise.resolve({ locale: "vi" }),
        searchParams: Promise.resolve({}),
      }),
    );
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Blog DoThesis");
    const chips = Array.from(container.querySelectorAll(".blog-chips a")).map((a) =>
      a.getAttribute("href"),
    );
    expect(chips).toEqual(["/blog/vi", "/blog/vi/chu-de/spss", "/blog/vi/chu-de/smartpls"]);
    expect(
      screen.getByRole("link", { name: "Cronbach's Alpha là gì" }).getAttribute("href"),
    ).toBe("/blog/vi/cronbach-alpha-la-gi");
  });

  test("pages through with ?page= and canonicalises each page to itself", async () => {
    stubApi({ total: 40 });
    render(
      await BlogListingPage({
        params: Promise.resolve({ locale: "vi" }),
        searchParams: Promise.resolve({ page: "2" }),
      }),
    );
    const pager = screen.getByRole("navigation", { name: "Phân trang" });
    expect(within(pager).getByRole("link", { name: "Trang sau" })).toBeTruthy();

    const meta = await listingMetadata({
      params: Promise.resolve({ locale: "vi" }),
      searchParams: Promise.resolve({ page: "2" }),
    });
    expect(meta.alternates?.canonical).toBe("http://localhost:3006/blog/vi?page=2");
  });

  test("an unknown locale is a 404, not an empty listing", async () => {
    stubApi();
    await expect(
      BlogListingPage({
        params: Promise.resolve({ locale: "de" }),
        searchParams: Promise.resolve({}),
      }),
    ).rejects.toThrow("NEXT_NOT_FOUND");
  });
});

describe("/blog/[locale]/chu-de/[category]", () => {
  async function renderCategory(opts: Parameters<typeof stubApi>[0] = {}, page?: string) {
    stubApi(opts);
    return render(
      await BlogCategoryPage({
        params: Promise.resolve({ locale: "vi", category: "spss" }),
        searchParams: Promise.resolve(page ? { page } : {}),
      }),
    );
  }

  test("leads with the display name and lists posts as rows, not a bare list", async () => {
    const { container } = await renderCategory();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("SPSS");
    const row = container.querySelector(".blog-row");
    expect(row).toBeTruthy();
    expect(
      within(row as HTMLElement)
        .getByRole("link", { name: "Cronbach's Alpha là gì" })
        .getAttribute("href"),
    ).toBe("/blog/vi/cronbach-alpha-la-gi");
    // A row carries the same three facts a listing card does, so the two pages
    // of the same site look related.
    expect(row?.querySelector(".blog-row__excerpt")?.textContent).toBe(
      "Một dòng cho trang danh sách.",
    );
    expect(row?.querySelector("time")?.getAttribute("datetime")).toBe(COMPACT.published_at);
    expect(row?.textContent).toContain("9 phút đọc");
  });

  test("sets only the intro's first paragraph as the lead, above the posts", async () => {
    const { container } = await renderCategory();
    const lead = container.querySelector(".blog-lead") as HTMLElement;
    expect(lead.textContent).toBe(
      "SPSS là phần mềm thống kê phổ biến nhất trong luận văn định lượng.",
    );
    expect(precedes(lead, container.querySelector(".blog-rows") as HTMLElement)).toBe(true);
    // The other four paragraphs are NOT in the hero — that wall of text under
    // the H1 is the whole reason this page was rebuilt.
    const hero = container.querySelector(".blog-hero") as HTMLElement;
    expect(hero.textContent).not.toContain("Bắt đầu từ đâu");
    expect(hero.textContent).not.toContain("tình huống hỏng");
  });

  test("keeps the rest of the intro under its own heading below the posts", async () => {
    const { container } = await renderCategory();
    const about = screen.getByRole("heading", { name: "Về chuyên mục này" });
    expect(precedes(container.querySelector(".blog-rows") as HTMLElement, about)).toBe(true);
    // Every word of the intro is still on the page, just further down.
    const section = container.querySelector(".blog-about") as HTMLElement;
    for (const paragraph of INTRO.split("\n\n").slice(1)) {
      expect(section.textContent).toContain(paragraph);
    }
  });

  test("states how many posts the category holds", async () => {
    const { container } = await renderCategory({ total: 41 });
    expect(container.querySelector(".blog-hero__count")?.textContent).toBe("41 bài viết");
  });

  test("an empty category says so instead of rendering an empty region", async () => {
    const { container } = await renderCategory({ posts: [], total: 0 });
    expect(screen.getByText("Chưa có bài viết trong chủ đề này.")).toBeTruthy();
    expect(container.querySelector(".blog-rows")).toBeNull();
    // "0 bài viết" over the empty message would say the same thing twice.
    expect(container.querySelector(".blog-hero__count")).toBeNull();
    // The orientation copy still ships: an empty hub is the one that needs it.
    expect(screen.getByRole("heading", { name: "Về chuyên mục này" })).toBeTruthy();
  });

  test("offers the sibling topics as chips rather than a stack of links", async () => {
    const { container } = await renderCategory();
    expect(screen.getByRole("heading", { name: "Chủ đề khác" })).toBeTruthy();
    const chips = Array.from(container.querySelectorAll(".blog-siblings .blog-chip"));
    expect(chips.map((c) => c.getAttribute("href"))).toEqual([
      "/blog/vi",
      "/blog/vi/chu-de/smartpls",
    ]);
    // Nothing in the footer row is the current page, so no chip is marked so.
    expect(chips.some((c) => c.getAttribute("aria-current"))).toBe(false);
    expect(container.querySelector(".blog-siblings .blog-linklist")).toBeNull();
  });

  test("self-canonicalises", async () => {
    stubApi();
    const meta = await categoryMetadata({
      params: Promise.resolve({ locale: "vi", category: "spss" }),
    });
    expect(meta.alternates?.canonical).toBe("http://localhost:3006/blog/vi/chu-de/spss");
    expect(meta.description).toContain("SPSS là phần mềm thống kê");
  });

  test("a slug outside the taxonomy is a 404", async () => {
    stubApi();
    await expect(
      BlogCategoryPage({
        params: Promise.resolve({ locale: "vi", category: "khong-co" }),
        searchParams: Promise.resolve({}),
      }),
    ).rejects.toThrow("NEXT_NOT_FOUND");
  });
});

describe("the category segment is the reader's own word for it", () => {
  test("the live Vietnamese URL keeps resolving, chips and pager included", async () => {
    stubApi({ total: 40 });
    const { container } = render(
      await BlogCategoryPage({
        params: Promise.resolve({ locale: "vi", category: "spss" }),
        searchParams: Promise.resolve({}),
      }),
    );
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("SPSS");
    expect(
      Array.from(container.querySelectorAll(".blog-hero .blog-chip")).map((c) =>
        c.getAttribute("href"),
      ),
    ).toEqual(["/blog/vi", "/blog/vi/chu-de/spss", "/blog/vi/chu-de/smartpls"]);
    const pager = screen.getByRole("navigation", { name: "Phân trang" });
    expect(within(pager).getByRole("link", { name: "Trang sau" }).getAttribute("href")).toBe(
      "/blog/vi/chu-de/spss?page=2",
    );
  });

  test("the English hub is served from /topic/ and links its own segment", async () => {
    stubApi();
    const { container } = render(
      await BlogTopicPage({
        params: Promise.resolve({ locale: "en", category: "spss" }),
        searchParams: Promise.resolve({}),
      }),
    );
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("SPSS");
    expect(
      Array.from(container.querySelectorAll(".blog-hero .blog-chip")).map((c) =>
        c.getAttribute("href"),
      ),
    ).toEqual(["/blog/en", "/blog/en/topic/spss", "/blog/en/topic/smartpls"]);
    const meta = await topicMetadata({ params: Promise.resolve({ locale: "en", category: "spss" }) });
    expect(meta.alternates?.canonical).toBe("http://localhost:3006/blog/en/topic/spss");
  });

  test("a hub reached through the other locale's segment 308s to its own", async () => {
    stubApi();
    await expect(
      BlogTopicPage({
        params: Promise.resolve({ locale: "vi", category: "spss" }),
        searchParams: Promise.resolve({}),
      }),
    ).rejects.toThrow("NEXT_PERMANENT_REDIRECT:/blog/vi/chu-de/spss");
    await expect(
      BlogCategoryPage({
        params: Promise.resolve({ locale: "en", category: "spss" }),
        searchParams: Promise.resolve({}),
      }),
    ).rejects.toThrow("NEXT_PERMANENT_REDIRECT:/blog/en/topic/spss");
    // No canonical for a URL that redirects — it would advertise the one URL
    // of the pair we are retiring.
    expect(
      await categoryMetadata({ params: Promise.resolve({ locale: "en", category: "spss" }) }),
    ).toEqual({});
  });
});

describe("/blog/[locale]/[slug]", () => {
  test("renders the title, the meta line, the body and the related list", async () => {
    stubApi();
    const { container } = render(
      await BlogPostPage({ params: Promise.resolve({ locale: "vi", slug: FULL.slug }) }),
    );
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Cronbach's Alpha là gì");
    expect(screen.getByText("1 tháng 9, 2026")).toBeTruthy();
    expect(screen.getByText("9 phút đọc")).toBeTruthy();
    expect(container.querySelector(".blog-tablewrap table")).not.toBeNull();
    expect(screen.getByRole("heading", { name: "Bài liên quan" })).toBeTruthy();
    // Exactly one CTA — more than one is a QA warning on the content side.
    expect(container.querySelectorAll('a[href="/landing"]')).toHaveLength(1);
  });

  test("the contents box links exactly the H2 ids the body renders", async () => {
    stubApi();
    const { container } = render(
      await BlogPostPage({ params: Promise.resolve({ locale: "vi", slug: FULL.slug }) }),
    );
    const toc = container.querySelector(".blog-toc");
    const hrefs = Array.from(toc?.querySelectorAll("a") ?? []).map((a) => a.getAttribute("href"));
    const ids = Array.from(container.querySelectorAll(".blog-prose h2")).map((h) => `#${h.id}`);
    expect(hrefs).toEqual(ids);
    expect(hrefs).toEqual(["#phan-tich-efa", "#do-tin-cay", "#cau-hoi-thuong-gap"]);
  });

  test("emits BlogPosting and a FAQPage carrying the body's questions", async () => {
    stubApi();
    const { container } = render(
      await BlogPostPage({ params: Promise.resolve({ locale: "vi", slug: FULL.slug }) }),
    );
    const blocks = Array.from(container.querySelectorAll('script[type="application/ld+json"]')).map(
      (s) => JSON.parse(s.innerHTML),
    );
    expect(blocks.map((b) => b["@type"])).toEqual(["BlogPosting", "FAQPage"]);
    expect(blocks[0].headline).toBe("Cronbach's Alpha là gì");
    expect(blocks[1].mainEntity.map((q: { name: string }) => q.name)).toEqual([
      "Alpha bao nhiêu là đạt?",
      "Loại biến nào trước?",
    ]);
  });

  test("a post with no FAQ section emits no FAQPage block", async () => {
    stubApi({
      detail: { post: { ...FULL, body: "## Mở đầu\n\nNội dung.\n" }, related: [], category: null },
    });
    const { container } = render(
      await BlogPostPage({ params: Promise.resolve({ locale: "vi", slug: FULL.slug }) }),
    );
    const types = Array.from(container.querySelectorAll('script[type="application/ld+json"]')).map(
      (s) => JSON.parse(s.innerHTML)["@type"],
    );
    expect(types).toEqual(["BlogPosting"]);
  });

  test("metadata carries the canonical, the article OG type and a share image", async () => {
    stubApi();
    const meta = await postMetadata({
      params: Promise.resolve({ locale: "vi", slug: FULL.slug }),
    });
    expect(meta.title).toBe("Cronbach's Alpha là gì | DoThesis");
    expect(meta.alternates?.canonical).toBe(
      "http://localhost:3006/blog/vi/cronbach-alpha-la-gi",
    );
    expect((meta.openGraph as { type?: string })?.type).toBe("article");
    expect(JSON.stringify(meta.openGraph)).toContain(
      "/blog/vi/cronbach-alpha-la-gi/opengraph-image",
    );
    expect((meta.twitter as { card?: string })?.card).toBe("summary_large_image");
  });

  test("renders no hero when the post has no image", async () => {
    stubApi();
    const { container } = render(
      await BlogPostPage({ params: Promise.resolve({ locale: "vi", slug: FULL.slug }) }),
    );
    expect(container.querySelector(".blog-article__hero")).toBeNull();
  });

  test("renders the library hero from the root-relative path the seed stores", async () => {
    stubApi({
      detail: {
        post: { ...FULL, image_url: "/img/blog/term-la-gi-2.webp" },
        related: [],
        category: CATEGORIES[0],
      },
    });
    const { container } = render(
      await BlogPostPage({ params: Promise.resolve({ locale: "vi", slug: FULL.slug }) }),
    );
    const hero = container.querySelector("img.blog-article__hero") as HTMLImageElement | null;
    // Root-relative in the <img> src: the browser has a page to resolve it
    // against, so baking an origin into the row would only pin the environment.
    expect(hero?.getAttribute("src")).toBe("/img/blog/term-la-gi-2.webp");
    expect(hero?.getAttribute("loading")).toBe("eager");
    expect(hero?.getAttribute("alt")).toBe("");
  });

  test("a root-relative hero reaches og:image and JSON-LD as an absolute url", async () => {
    stubApi({
      detail: {
        post: { ...FULL, image_url: "/img/blog/term-la-gi-2.webp" },
        related: [],
        category: CATEGORIES[0],
      },
    });
    const meta = await postMetadata({
      params: Promise.resolve({ locale: "vi", slug: FULL.slug }),
    });
    expect(JSON.stringify(meta.openGraph)).toContain(
      "http://localhost:3006/img/blog/term-la-gi-2.webp",
    );

    const { container } = render(
      await BlogPostPage({ params: Promise.resolve({ locale: "vi", slug: FULL.slug }) }),
    );
    const ld = JSON.parse(
      container.querySelector('script[type="application/ld+json"]')?.innerHTML ?? "{}",
    );
    expect(ld.image).toEqual(["http://localhost:3006/img/blog/term-la-gi-2.webp"]);
  });

  test("an unknown slug is a 404 and its metadata is noindex", async () => {
    server.use(
      http.post("*/api/v1/blog/get", () =>
        HttpResponse.json({ detail: { error: { code: "not_found" } } }, { status: 404 }),
      ),
    );
    await expect(
      BlogPostPage({ params: Promise.resolve({ locale: "vi", slug: "khong-co" }) }),
    ).rejects.toThrow("NEXT_NOT_FOUND");
    const meta = await postMetadata({
      params: Promise.resolve({ locale: "vi", slug: "khong-co" }),
    });
    expect((meta.robots as { index?: boolean })?.index).toBe(false);
  });
});

describe("sitemap and robots", () => {
  test("lists the marketing home, the listing, every category and every post", async () => {
    server.use(
      http.post("*/api/v1/blog/categories", () => HttpResponse.json({ categories: CATEGORIES })),
      http.post("*/api/v1/blog/sitemap", () =>
        HttpResponse.json({
          posts: [
            { locale: "vi", slug: "cronbach-alpha-la-gi", updated_at: "2026-09-05T00:00:00Z" },
          ],
        }),
      ),
    );
    const rows = await sitemap();
    const urls = rows.map((r) => r.url);
    expect(urls).toContain("http://localhost:3006/");
    expect(urls).toContain("http://localhost:3006/blog/vi");
    expect(urls).toContain("http://localhost:3006/blog/vi/chu-de/spss");
    expect(urls).toContain("http://localhost:3006/blog/vi/chu-de/smartpls");
    expect(urls).toContain("http://localhost:3006/blog/vi/cronbach-alpha-la-gi");
    const post = rows.find((r) => r.url.endsWith("cronbach-alpha-la-gi"));
    expect((post?.lastModified as Date).toISOString()).toBe("2026-09-05T00:00:00.000Z");
  });

  test("a dead API still yields the static pages instead of a broken sitemap", async () => {
    server.use(
      http.post("*/api/v1/blog/sitemap", () => HttpResponse.json({}, { status: 500 })),
      http.post("*/api/v1/blog/categories", () => HttpResponse.json({}, { status: 500 })),
    );
    const urls = (await sitemap()).map((r) => r.url);
    expect(urls).toEqual(["http://localhost:3006/", "http://localhost:3006/blog/vi"]);
  });

  test("robots opens the public surfaces and closes the auth-gated ones", async () => {
    // No split configured in the test environment, so every host gets the
    // marketing answer. The app-host case lives in app/lib/hosts.test.ts,
    // which owns the routing rules.
    const r = await robots();
    const rule = Array.isArray(r.rules) ? r.rules[0] : r.rules;
    expect(rule.allow).toEqual(["/blog", "/landing"]);
    expect(rule.disallow).toEqual(["/chat", "/admin", "/api"]);
    expect(r.sitemap).toBe("http://localhost:3006/sitemap.xml");
  });
});
