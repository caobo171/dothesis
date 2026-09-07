import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { extractHeadings } from "../_lib/markdown";
import { Markdown } from "./Markdown";

describe("Markdown", () => {
  test("gives headings the same ids the contents box links to", () => {
    const body = "## Phân tích EFA\n\nNội dung.\n\n## Độ tin cậy\n\nNội dung.\n\n## Phân tích EFA\n\nLại nữa.\n";
    const { container } = render(<Markdown>{body}</Markdown>);
    const rendered = Array.from(container.querySelectorAll("h2")).map((h) => h.id);
    expect(rendered).toEqual(["phan-tich-efa", "do-tin-cay", "phan-tich-efa-1"]);
    // The renderer and the standalone extractor must never disagree — that is
    // the whole reason the extractor exists.
    expect(rendered).toEqual(extractHeadings(body, [2]).map((h) => h.id));
  });

  test("wraps tables so a wide table scrolls instead of the page", () => {
    const { container } = render(
      <Markdown>{"| Chỉ số | Ngưỡng |\n| --- | --- |\n| Alpha | 0.7 |\n"}</Markdown>,
    );
    const table = container.querySelector("table");
    expect(table).not.toBeNull();
    expect(table?.parentElement?.className).toContain("blog-tablewrap");
    expect(screen.getByText("Alpha")).toBeTruthy();
  });

  test("external links open in a new tab without handing it window.opener", () => {
    const { container } = render(
      <Markdown>{"[Hair](https://example.com/a) và [EFA](/blog/vi/efa)\n"}</Markdown>,
    );
    const external = container.querySelector('a[href="https://example.com/a"]');
    expect(external?.getAttribute("rel")).toContain("noopener");
    expect(external?.getAttribute("target")).toBe("_blank");

    const internal = container.querySelector('a[href="/blog/vi/efa"]');
    expect(internal?.getAttribute("target")).toBeNull();
  });

  test("images are lazy — a post body is below the fold by definition", () => {
    const { container } = render(<Markdown>{"![Biểu đồ](/x.png)\n"}</Markdown>);
    const img = container.querySelector("img");
    expect(img?.getAttribute("loading")).toBe("lazy");
    expect(img?.getAttribute("alt")).toBe("Biểu đồ");
  });

  test("renders GFM tables and lists rather than escaping them", () => {
    const { container } = render(<Markdown>{"- một\n- hai\n"}</Markdown>);
    expect(container.querySelectorAll("li")).toHaveLength(2);
  });
});
