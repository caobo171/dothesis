import { describe, expect, test } from "vitest";

import {
  SITE_ORIGIN,
  absoluteUrl,
  blogPath,
  categoryPath,
  categorySegment,
  listingPath,
  ogImagePath,
  postPath,
} from "./site";

describe("site", () => {
  test("defaults to the dev origin with no trailing slash", () => {
    expect(SITE_ORIGIN).toBe("http://localhost:3006");
  });

  test("builds the public blog routes", () => {
    expect(blogPath("vi")).toBe("/blog/vi");
    expect(postPath("vi", "cronbach-alpha-la-gi")).toBe("/blog/vi/cronbach-alpha-la-gi");
    expect(categoryPath("vi", "spss")).toBe("/blog/vi/chu-de/spss");
    expect(ogImagePath("vi", "x")).toBe("/blog/vi/x/opengraph-image");
  });

  test("the category segment is the reader's own word for it", () => {
    expect(categorySegment("vi")).toBe("chu-de");
    expect(categorySegment("en")).toBe("topic");
    // The live Vietnamese URLs are what 420 published posts link to; a locale
    // nobody configured must not invent a segment that 404s.
    expect(categorySegment("de")).toBe("chu-de");
  });

  test("the English category URL says topic, the Vietnamese one still says chu-de", () => {
    expect(categoryPath("en", "spss")).toBe("/blog/en/topic/spss");
    expect(categoryPath("vi", "spss")).toBe("/blog/vi/chu-de/spss");
  });

  test("page 1 has no ?page= so it cannot duplicate the bare listing", () => {
    expect(listingPath("vi")).toBe("/blog/vi");
    expect(listingPath("vi", 1)).toBe("/blog/vi");
    expect(listingPath("vi", 3)).toBe("/blog/vi?page=3");
  });

  test("a search keeps its query when it pages, and q comes first", () => {
    expect(listingPath("vi", 1, "alpha")).toBe("/blog/vi?q=alpha");
    expect(listingPath("vi", 2, "alpha")).toBe("/blog/vi?q=alpha&page=2");
    // The form produces the query in this order, so a link that pages must too:
    // two orderings of the same parameters are two URLs for one result set.
    expect(listingPath("vi", 2, "cỡ mẫu")).toBe("/blog/vi?q=c%E1%BB%A1+m%E1%BA%ABu&page=2");
    expect(listingPath("vi", 2, "")).toBe("/blog/vi?page=2");
  });

  test("absoluteUrl prefixes paths and leaves absolute URLs alone", () => {
    expect(absoluteUrl("/blog/vi")).toBe("http://localhost:3006/blog/vi");
    expect(absoluteUrl("https://dothesis.io/x")).toBe("https://dothesis.io/x");
  });
});
