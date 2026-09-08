import { describe, expect, test } from "vitest";

import type { FullPost } from "./api";
import { blogPostingJsonLd, faqJsonLd } from "./jsonld";
import { extractFaq } from "./markdown";

const POST: FullPost = {
  slug: "cronbach-alpha-la-gi",
  locale: "vi",
  title: "Cronbach's Alpha là gì",
  excerpt: "Một dòng.",
  image_url: null,
  category: { slug: "spss", display_name: "SPSS" },
  tags: ["cronbach alpha", "spss"],
  published_at: "2026-09-01T03:00:00Z",
  reading_time: 9,
  focus_keyword: "cronbach alpha",
  body: "## Câu hỏi thường gặp\n\n### Bao nhiêu là đạt?\n\nTừ 0.7 trở lên.\n",
  meta_title: "Cronbach's Alpha là gì | DoThesis",
  meta_description: "Mô tả.",
  canonical_url: null,
  updated_at: "2026-09-05T03:00:00Z",
  secondary_keywords: [],
  archetype: "term-la-gi",
};

describe("blogPostingJsonLd", () => {
  const ld = blogPostingJsonLd(POST) as Record<string, any>;

  test("identifies the article by its absolute canonical URL", () => {
    const url = "http://localhost:3006/blog/vi/cronbach-alpha-la-gi";
    expect(ld["@type"]).toBe("BlogPosting");
    expect(ld["@id"]).toBe(`${url}#article`);
    expect(ld.url).toBe(url);
    expect(ld.mainEntityOfPage["@id"]).toBe(url);
  });

  test("carries the dates as ISO 8601 and the language as a BCP 47 tag", () => {
    expect(ld.datePublished).toBe("2026-09-01T03:00:00.000Z");
    expect(ld.dateModified).toBe("2026-09-05T03:00:00.000Z");
    expect(ld.inLanguage).toBe("vi-VN");
  });

  test("names a publisher and an article section", () => {
    expect(ld.publisher.name).toBe("DoThesis");
    expect(ld.articleSection).toBe("SPSS");
    expect(ld.timeRequired).toBe("PT9M");
    expect(ld.keywords).toBe("cronbach alpha, spss");
  });

  test("falls back to published_at when a post was never edited", () => {
    const ld2 = blogPostingJsonLd({ ...POST, updated_at: null }) as Record<string, any>;
    expect(ld2.dateModified).toBe(ld2.datePublished);
  });

  test("honours a post's own canonical_url over the derived one", () => {
    const ld2 = blogPostingJsonLd({
      ...POST,
      canonical_url: "https://dothesis.io/blog/vi/x",
    }) as Record<string, any>;
    expect(ld2.url).toBe("https://dothesis.io/blog/vi/x");
  });

  test("makes a root-relative image absolute, and leaves an absolute one alone", () => {
    const relative = blogPostingJsonLd({
      ...POST,
      image_url: "/img/blog/term-la-gi-2.webp",
    }) as Record<string, any>;
    expect(relative.image).toEqual(["http://localhost:3006/img/blog/term-la-gi-2.webp"]);

    const absolute = blogPostingJsonLd({
      ...POST,
      image_url: "https://cdn.example.com/a.webp",
    }) as Record<string, any>;
    expect(absolute.image).toEqual(["https://cdn.example.com/a.webp"]);
  });

  test("emits no empty keys for the fields a post may not have", () => {
    const bare = blogPostingJsonLd({
      ...POST,
      tags: [],
      image_url: null,
      category: null,
      published_at: null,
      updated_at: null,
    }) as Record<string, any>;
    for (const k of ["keywords", "image", "articleSection", "datePublished", "dateModified"]) {
      expect(k in bare).toBe(false);
    }
  });
});

describe("faqJsonLd", () => {
  test("mirrors the questions the body actually renders", () => {
    const ld = faqJsonLd(extractFaq(POST.body), POST) as Record<string, any>;
    expect(ld["@type"]).toBe("FAQPage");
    expect(ld.mainEntity).toHaveLength(1);
    expect(ld.mainEntity[0].name).toBe("Bao nhiêu là đạt?");
    expect(ld.mainEntity[0].acceptedAnswer.text).toBe("Từ 0.7 trở lên.");
  });

  test("a post with no FAQ gets no FAQPage block at all", () => {
    expect(faqJsonLd([], POST)).toBeNull();
  });
});
