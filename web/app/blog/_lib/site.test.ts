import { describe, expect, test } from "vitest";

import {
  SITE_ORIGIN,
  absoluteUrl,
  blogPath,
  categoryPath,
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

  test("page 1 has no ?page= so it cannot duplicate the bare listing", () => {
    expect(listingPath("vi")).toBe("/blog/vi");
    expect(listingPath("vi", 1)).toBe("/blog/vi");
    expect(listingPath("vi", 3)).toBe("/blog/vi?page=3");
  });

  test("absoluteUrl prefixes paths and leaves absolute URLs alone", () => {
    expect(absoluteUrl("/blog/vi")).toBe("http://localhost:3006/blog/vi");
    expect(absoluteUrl("https://dothesis.io/x")).toBe("https://dothesis.io/x");
  });
});
