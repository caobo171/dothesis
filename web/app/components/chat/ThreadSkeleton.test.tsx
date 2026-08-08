import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";

import { ThreadSkeleton } from "./ThreadSkeleton";

describe("ThreadSkeleton", () => {
  test("bubble rows carry a definite width, not just a max", () => {
    // The lines inside are sized in PERCENTAGES. With only a max-width the row
    // shrinks to fit its content, so those percentages resolve against a width
    // that does not exist and every bubble collapsed into a thin vertical pill.
    const { container } = render(<ThreadSkeleton />);
    const rows = Array.from(container.querySelectorAll("[class*='self-']"));
    expect(rows.length).toBeGreaterThan(0);
    for (const row of rows) {
      const cls = row.className;
      expect(cls).toMatch(/(^|\s)w-\[\d+%\]/);      // definite width present
      expect(cls).not.toMatch(/max-w-\[\d+%\]/);     // and not only a max
    }
  });

  test("announces itself as busy for screen readers", () => {
    render(<ThreadSkeleton label="Đang mở cuộc trò chuyện…" />);
    expect(screen.getByLabelText("Đang mở cuộc trò chuyện…")).toBeTruthy();
  });
});
