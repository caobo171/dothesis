import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { describe, expect, test } from "vitest";

import {
  HeadingSlugger,
  extractFaq,
  extractHeadings,
  plainText,
  readingTime,
  slugify,
  tableOfContents,
} from "./markdown";

const here = path.dirname(fileURLToPath(import.meta.url));

function fixture(name: string) {
  return {
    md: readFileSync(path.join(here, `__fixtures__/${name}.md`), "utf8"),
    expected: JSON.parse(
      readFileSync(path.join(here, `__fixtures__/${name}.json`), "utf8"),
    ) as {
      headings: Array<{ level: number; text: string; id: string }>;
      faq_questions?: string[];
    },
  };
}

// The shared contract, copied byte for byte from api/tests/fixtures/blog/.
// Both implementations parse this file; if they ever disagree, one of them has
// broken every in-page anchor on the blog.
const SHARED = fixture("headings");
// Cases the shared fixture does not reach, all of them web-side rendering
// concerns: a heading inside a code fence, inline markup, a heading that is a
// link, and long punctuation runs.
const EDGE = fixture("headings-edge");
const FIXTURE_MD = EDGE.md;
const FIXTURE_EXPECTED = EDGE.expected;

describe("slugify", () => {
  test("strips Vietnamese diacritics and maps đ to d", () => {
    expect(slugify("Phân tích EFA")).toBe("phan-tich-efa");
    expect(slugify("Độ tin cậy")).toBe("do-tin-cay");
    expect(slugify("Đánh giá mô hình đo lường")).toBe("danh-gia-mo-hinh-do-luong");
  });

  test("collapses and trims punctuation runs", () => {
    expect(slugify("Kiểm định t-test / ANOVA (SPSS 29)")).toBe(
      "kiem-dinh-t-test-anova-spss-29",
    );
    expect(slugify("  ...  ")).toBe("");
  });
});

describe("HeadingSlugger", () => {
  test("suffixes repeats with -1 and -2", () => {
    const s = new HeadingSlugger();
    expect(s.slug("Phân tích EFA")).toBe("phan-tich-efa");
    expect(s.slug("Phân tích EFA")).toBe("phan-tich-efa-1");
    expect(s.slug("Phan tich EFA")).toBe("phan-tich-efa-2");
  });

  test("never hands out an id that a later heading already claimed", () => {
    const s = new HeadingSlugger();
    expect(s.slug("efa")).toBe("efa");
    expect(s.slug("efa 1")).toBe("efa-1");
    // The second "efa" cannot take "efa-1" — it is already an anchor.
    expect(s.slug("efa")).toBe("efa-2");
  });
});

describe("extractHeadings", () => {
  test("matches the shared api fixture byte for byte", () => {
    expect(extractHeadings(SHARED.md)).toEqual(SHARED.expected.headings);
  });

  test("finds the same FAQ questions the api fixture declares", () => {
    expect(extractFaq(SHARED.md).map((f) => f.question)).toEqual(
      SHARED.expected.faq_questions,
    );
  });

  test("matches the web edge-case fixture byte for byte", () => {
    expect(extractHeadings(FIXTURE_MD)).toEqual(FIXTURE_EXPECTED.headings);
  });

  test("ignores headings inside fenced code blocks", () => {
    const ids = extractHeadings(FIXTURE_MD).map((h) => h.id);
    expect(ids).not.toContain("day-khong-phai-tieu-de");
  });
});

describe("tableOfContents", () => {
  test("returns only H2s, in document order, with the rendered ids", () => {
    const toc = tableOfContents(FIXTURE_MD);
    expect(toc.every((h) => h.level === 2)).toBe(true);
    expect(toc.map((h) => h.id)).toEqual([
      "phan-tich-efa",
      "do-tin-cay-cua-thang-do",
      "danh-gia-mo-hinh-do-luong",
      "phan-tich-efa-1",
      "phan-tich-efa-2",
      "kiem-dinh-t-test-anova-spss-29",
      "doc-them-ve-pls-sem",
      "cau-hoi-thuong-gap",
    ]);
  });
});

describe("extractFaq", () => {
  test("pulls the H3 questions under the FAQ H2", () => {
    const faq = extractFaq(FIXTURE_MD);
    expect(faq).toHaveLength(4);
    expect(faq[0].question).toBe("Cronbach's Alpha bao nhiêu là đạt?");
    expect(faq[0].answer).toContain("Từ 0.7 trở lên");
    // Both paragraphs of a multi-paragraph answer are kept.
    expect(faq[0].answer).toContain("Đoạn thứ hai");
    expect(faq[3].question).toBe("Alpha quá cao có sao không?");
  });

  test("returns nothing when the post has no FAQ section", () => {
    expect(extractFaq("## Mở đầu\n\nNội dung.\n")).toEqual([]);
  });
});

describe("plainText and readingTime", () => {
  test("plainText drops markdown syntax but keeps the words", () => {
    const out = plainText("## Tiêu đề\n\nMột **đoạn** với [liên kết](/blog/vi/x) và `mã`.\n");
    expect(out).toBe("Tiêu đề Một đoạn với liên kết và mã.");
  });

  test("readingTime rounds up at 200 words per minute and never returns 0", () => {
    expect(readingTime("một hai ba")).toBe(1);
    expect(readingTime(Array(401).fill("từ").join(" "))).toBe(3);
  });
});
