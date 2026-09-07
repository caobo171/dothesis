import { render, screen, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import type { BlogCategory, CompactPost } from "../_lib/api";
import { extractFaq, tableOfContents } from "../_lib/markdown";
import { blogPostingJsonLd, faqJsonLd } from "../_lib/jsonld";
import { BlogShell } from "./BlogShell";
import { CategoryChips } from "./CategoryChips";
import { ContentsBox } from "./ContentsBox";
import { CtaBlock } from "./CtaBlock";
import { JsonLd } from "./JsonLd";
import { Pagination, pageWindow } from "./Pagination";
import { PostCard } from "./PostCard";

const POST: CompactPost = {
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

const CATEGORIES: BlogCategory[] = [
  { slug: "spss", name: "SPSS", display_name: "SPSS", intro_md: "", post_count: 20 },
  { slug: "smartpls", name: "SmartPLS", display_name: "SmartPLS", intro_md: "", post_count: 0 },
];

describe("PostCard", () => {
  test("links the title, the category and falls back to the generated OG thumbnail", () => {
    const { container } = render(<PostCard post={POST} />);
    expect(
      screen.getByRole("link", { name: "Cronbach's Alpha là gì" }).getAttribute("href"),
    ).toBe("/blog/vi/cronbach-alpha-la-gi");
    expect(screen.getByRole("link", { name: "SPSS" }).getAttribute("href")).toBe(
      "/blog/vi/chu-de/spss",
    );
    expect(container.querySelector("img")?.getAttribute("src")).toBe(
      "/blog/vi/cronbach-alpha-la-gi/opengraph-image",
    );
  });

  test("dates the post in the readership's timezone and shows reading time", () => {
    render(<PostCard post={POST} />);
    expect(screen.getByText("1 tháng 9, 2026")).toBeTruthy();
    expect(screen.getByText("9 phút đọc")).toBeTruthy();
  });

  test("prefers a real image when the post has one", () => {
    const { container } = render(
      <PostCard post={{ ...POST, image_url: "https://cdn.example.com/a.png" }} />,
    );
    expect(container.querySelector("img")?.getAttribute("src")).toBe(
      "https://cdn.example.com/a.png",
    );
  });
});

describe("ContentsBox", () => {
  const body = "## Phân tích EFA\n\nx\n\n## Độ tin cậy\n\ny\n\n## Câu hỏi thường gặp\n\nz\n";

  test("links every H2 by the id the body renders", () => {
    render(<ContentsBox headings={tableOfContents(body)} locale="vi" />);
    const links = screen.getAllByRole("link");
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "#phan-tich-efa",
      "#do-tin-cay",
      "#cau-hoi-thuong-gap",
    ]);
  });

  test("stays out of the way when there is only one section", () => {
    const { container } = render(
      <ContentsBox headings={tableOfContents("## Chỉ một\n\nx\n")} locale="vi" />,
    );
    expect(container.querySelector("nav")).toBeNull();
  });
});

describe("Pagination", () => {
  test("windows the page numbers around the current one", () => {
    expect(pageWindow(1, 3)).toEqual([1, 2, 3]);
    expect(pageWindow(6, 20)).toEqual([1, "gap", 5, 6, 7, "gap", 20]);
  });

  test("renders real anchors with rel prev/next and marks the current page", () => {
    render(
      <Pagination
        page={2}
        total={40}
        pageSize={12}
        locale="vi"
        hrefFor={(p) => (p > 1 ? `/blog/vi?page=${p}` : "/blog/vi")}
      />,
    );
    expect(screen.getByRole("link", { name: "Trang trước" }).getAttribute("href")).toBe(
      "/blog/vi",
    );
    expect(screen.getByRole("link", { name: "Trang sau" }).getAttribute("href")).toBe(
      "/blog/vi?page=3",
    );
    const nav = screen.getByRole("navigation", { name: "Phân trang" });
    expect(within(nav).getByText("2").getAttribute("aria-current")).toBe("page");
  });

  test("disappears when everything fits on one page", () => {
    const { container } = render(
      <Pagination page={1} total={5} pageSize={12} locale="vi" hrefFor={() => "/blog/vi"} />,
    );
    expect(container.querySelector("nav")).toBeNull();
  });
});

describe("CategoryChips", () => {
  test("marks the active category and links the rest", () => {
    render(<CategoryChips categories={CATEGORIES} locale="vi" active="spss" />);
    expect(screen.getByRole("link", { name: /^SPSS/ }).getAttribute("aria-current")).toBe(
      "page",
    );
    expect(screen.getByRole("link", { name: "SmartPLS" }).getAttribute("href")).toBe(
      "/blog/vi/chu-de/smartpls",
    );
    // A category with no posts shows no count rather than a "0".
    expect(screen.queryByText("0")).toBeNull();
  });

  test('marks "Tất cả" when no category is active', () => {
    render(<CategoryChips categories={CATEGORIES} locale="vi" />);
    expect(screen.getByRole("link", { name: "Tất cả" }).getAttribute("aria-current")).toBe(
      "page",
    );
  });
});

describe("CtaBlock", () => {
  test("ships exactly one CTA link, pointed at the landing page", () => {
    const { container } = render(<CtaBlock locale="vi" />);
    const links = container.querySelectorAll("a");
    expect(links).toHaveLength(1);
    expect(links[0].getAttribute("href")).toBe("/landing");
  });
});

describe("JsonLd", () => {
  test("escapes < so a body containing </script> cannot break out of the tag", () => {
    const { container } = render(<JsonLd data={{ headline: "Dùng </script> trong form" }} />);
    const raw = container.querySelector("script")?.innerHTML ?? "";
    expect(raw).not.toContain("</script>");
    expect(JSON.parse(raw).headline).toBe("Dùng </script> trong form");
  });

  test("renders nothing for a post with no FAQ", () => {
    const { container } = render(<JsonLd data={faqJsonLd([], { locale: "vi", slug: "x", canonical_url: null })} />);
    expect(container.querySelector("script")).toBeNull();
  });

  test("the FAQ block only ever lists questions the body renders", () => {
    const body = "## Câu hỏi thường gặp\n\n### Bao nhiêu là đạt?\n\nTừ 0.7.\n";
    const ld = faqJsonLd(extractFaq(body), { locale: "vi", slug: "x", canonical_url: null }) as any;
    expect(ld.mainEntity.map((q: any) => q.name)).toEqual(["Bao nhiêu là đạt?"]);
    expect(blogPostingJsonLd({ ...POST, body, meta_title: "t", meta_description: "d", canonical_url: null, updated_at: null, focus_keyword: "cronbach alpha", secondary_keywords: [], archetype: null })["@type"]).toBe("BlogPosting");
  });
});

describe("BlogShell", () => {
  test("wraps the page in the landing design scope with its nav and footer", () => {
    const { container } = render(
      <BlogShell>
        <p>bài viết</p>
      </BlogShell>,
    );
    expect(container.querySelector(".lp-root")).not.toBeNull();
    expect(screen.getByRole("banner")).toBeTruthy();
    expect(screen.getByRole("contentinfo")).toBeTruthy();
    expect(screen.getByText("bài viết")).toBeTruthy();
  });
});
