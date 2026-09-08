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
  splitLead,
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

describe("splitLead", () => {
  // The shape every one of the seven live category intros has: five plain
  // paragraphs, blank line between them.
  const INTRO = [
    "Một bài luận văn định lượng chỉ dùng chừng hai chục khái niệm thống kê.",
    "",
    "Chuyên mục này giải thích từng khái niệm bằng ngôn ngữ người viết cần.",
    "",
    "Bắt đầu từ đâu. Đọc bài về thống kê mô tả trước.",
    "",
  ].join("\n");

  test("leads with the first paragraph and keeps the rest", () => {
    const { lead, rest } = splitLead(INTRO);
    expect(lead).toBe("Một bài luận văn định lượng chỉ dùng chừng hai chục khái niệm thống kê.");
    expect(rest).toContain("Chuyên mục này giải thích");
    expect(rest).toContain("Bắt đầu từ đâu");
    // Nothing is dropped on the floor: every word is on the page, somewhere.
    expect(`${lead}\n\n${rest}`).toBe(INTRO.trim());
  });

  test("a paragraph hard-wrapped over several lines stays one lead", () => {
    const { lead, rest } = splitLead(
      "Câu thứ nhất của đoạn mở đầu,\nvà câu thứ hai xuống dòng.\n\nĐoạn hai.",
    );
    expect(lead).toBe("Câu thứ nhất của đoạn mở đầu,\nvà câu thứ hai xuống dòng.");
    expect(rest).toBe("Đoạn hai.");
  });

  test("a one-paragraph intro is all lead and no remainder", () => {
    expect(splitLead("Chỉ có một đoạn.\n")).toEqual({ lead: "Chỉ có một đoạn.", rest: "" });
  });

  test("leading blank lines belong to neither half", () => {
    expect(splitLead("\n\n  \nĐoạn đầu.\n\nĐoạn hai.")).toEqual({
      lead: "Đoạn đầu.",
      rest: "Đoạn hai.",
    });
  });

  test("empty input gives two empty halves", () => {
    expect(splitLead("")).toEqual({ lead: "", rest: "" });
    expect(splitLead("\n  \n")).toEqual({ lead: "", rest: "" });
  });

  // The whole point of the block scan: a lead that swallowed one of these
  // would look worse than the wall of text it replaced, so there is no lead.
  test.each([
    ["a heading", "## Bắt đầu từ đâu\n\nĐoạn sau tiêu đề."],
    ["a bullet list", "- Điểm một\n- Điểm hai\n\nĐoạn sau."],
    ["an ordered list", "1. Điểm một\n2. Điểm hai\n\nĐoạn sau."],
    ["a blockquote", "> Trích dẫn.\n\nĐoạn sau."],
    ["a code fence", "```\nSPSS\n```\n\nĐoạn sau."],
    ["a thematic break", "---\n\nĐoạn sau."],
    ["indented code", "    alpha = 0.7\n\nĐoạn sau."],
    ["raw HTML", "<div>Khối HTML</div>\n\nĐoạn sau."],
    ["a table", "| Chỉ số | Ngưỡng |\n| --- | --- |\n| Alpha | 0.7 |\n\nĐoạn sau."],
    ["a setext heading", "Bắt đầu từ đâu\n===\n\nĐoạn sau."],
    ["a setext h2", "Bắt đầu từ đâu\n---\n\nĐoạn sau."],
  ])("returns no lead when the intro opens with %s", (_name, md) => {
    const { lead, rest } = splitLead(md);
    expect(lead).toBe("");
    expect(rest).toBe(md.trim());
  });

  test("stops the lead at a heading that follows with no blank line", () => {
    const { lead, rest } = splitLead("Đoạn mở đầu.\n## Mục tiếp theo\n\nNội dung.");
    expect(lead).toBe("Đoạn mở đầu.");
    expect(rest).toBe("## Mục tiếp theo\n\nNội dung.");
  });

  test("a fence opened right under the lead is not pulled into it", () => {
    const { lead, rest } = splitLead("Đoạn mở đầu.\n```\nalpha\n```");
    expect(lead).toBe("Đoạn mở đầu.");
    expect(rest).toBe("```\nalpha\n```");
  });
});
