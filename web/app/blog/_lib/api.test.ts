import { http, HttpResponse } from "msw";
import { describe, expect, test } from "vitest";

import { server } from "../../../tests/setup";
import {
  fetchCategories,
  fetchPost,
  fetchPosts,
  fetchSitemap,
} from "./api";

const COMPACT = {
  slug: "cronbach-alpha-la-gi",
  locale: "vi",
  title: "Cronbach's Alpha là gì",
  excerpt: "Một dòng cho trang danh sách.",
  image_url: null,
  category: { slug: "spss", display_name: "SPSS" },
  tags: ["cronbach alpha"],
  published_at: "2026-09-01T00:00:00Z",
  reading_time: 9,
  focus_keyword: "cronbach alpha",
};

describe("fetchPosts", () => {
  test("posts the listing filters in the body and returns the page", async () => {
    let seen: unknown = null;
    server.use(
      http.post("*/api/v1/blog/list", async ({ request }) => {
        seen = await request.json();
        return HttpResponse.json({ posts: [COMPACT], total: 1, page: 2, page_size: 12 });
      }),
    );
    const out = await fetchPosts({ locale: "vi", page: 2, category: "spss" });
    expect(out.posts[0].slug).toBe("cronbach-alpha-la-gi");
    expect(out.total).toBe(1);
    expect(seen).toMatchObject({ locale: "vi", page: 2, category: "spss" });
  });

  test("omits absent filters rather than sending nulls", async () => {
    let seen: Record<string, unknown> = {};
    server.use(
      http.post("*/api/v1/blog/list", async ({ request }) => {
        seen = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ posts: [], total: 0, page: 1, page_size: 12 });
      }),
    );
    await fetchPosts({ locale: "vi" });
    expect("category" in seen).toBe(false);
    expect("q" in seen).toBe(false);
  });
});

describe("fetchPost", () => {
  test("returns the post with its related list and category", async () => {
    server.use(
      http.post("*/api/v1/blog/get", () =>
        HttpResponse.json({
          post: { ...COMPACT, body: "## Mở đầu\n", meta_title: "t", meta_description: "d" },
          related: [COMPACT],
          category: { slug: "spss", name: "SPSS", display_name: "SPSS", intro_md: "", post_count: 12 },
        }),
      ),
    );
    const out = await fetchPost("vi", "cronbach-alpha-la-gi");
    expect(out?.post.body).toContain("Mở đầu");
    expect(out?.related).toHaveLength(1);
    expect(out?.category?.slug).toBe("spss");
  });

  test("a 404 is 'no such post', not an error", async () => {
    server.use(
      http.post("*/api/v1/blog/get", () =>
        HttpResponse.json({ detail: { error: { code: "not_found", message: "x" } } }, { status: 404 }),
      ),
    );
    expect(await fetchPost("vi", "khong-ton-tai")).toBeNull();
  });

  test("a 500 propagates so the route renders an error, not a soft 404", async () => {
    server.use(
      http.post("*/api/v1/blog/get", () => HttpResponse.json({}, { status: 500 })),
    );
    await expect(fetchPost("vi", "cronbach-alpha-la-gi")).rejects.toThrow();
  });
});

describe("fetchCategories and fetchSitemap", () => {
  test("categories come back as a list", async () => {
    server.use(
      http.post("*/api/v1/blog/categories", () =>
        HttpResponse.json({
          categories: [
            { slug: "spss", name: "SPSS", display_name: "SPSS", intro_md: "Giới thiệu", post_count: 20 },
          ],
        }),
      ),
    );
    const cats = await fetchCategories("vi");
    expect(cats[0].post_count).toBe(20);
  });

  test("the sitemap feed tolerates an empty payload", async () => {
    server.use(http.post("*/api/v1/blog/sitemap", () => HttpResponse.json({})));
    expect(await fetchSitemap()).toEqual([]);
  });
});
