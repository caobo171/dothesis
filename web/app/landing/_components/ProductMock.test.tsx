import { describe, expect, test, beforeEach, afterEach, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";

import { ProductMock } from "./ProductMock";

/**
 * jsdom's matchMedia never evaluates the query — it answers `false` to
 * everything — so a reduced-motion test has to install its own. This also
 * keeps the two cases symmetrical: the same stub, one boolean apart.
 */
function stubMatchMedia(matches: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
      onchange: null,
    })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("ProductMock", () => {
  describe("prefers-reduced-motion: reduce", () => {
    beforeEach(() => {
      stubMatchMedia(true);
    });

    test("lands on the finished draft instead of writing it out", () => {
      render(<ProductMock />);

      // The last step's caption and badge — the outcome, without the
      // choreography that produced it.
      expect(screen.getByText(/draft complete/i)).toBeInTheDocument();
      expect(screen.getByText("Draft ready")).toBeInTheDocument();
      expect(screen.queryByText(/Reading your idea/)).toBeNull();
    });

    test("offers no Replay, because there is no sequence to replay", () => {
      render(<ProductMock />);

      expect(screen.queryByRole("button", { name: /replay/i })).toBeNull();
    });

    test("stays on the finished draft — the timer never runs", () => {
      vi.useFakeTimers();
      render(<ProductMock />);

      act(() => {
        vi.advanceTimersByTime(30_000);
      });

      expect(screen.getByText("Draft ready")).toBeInTheDocument();
    });
  });

  describe("motion allowed", () => {
    beforeEach(() => {
      stubMatchMedia(false);
    });

    test("opens on the idea and writes the modules out", () => {
      vi.useFakeTimers();
      render(<ProductMock />);

      // The idea card's quote, which only step 0 renders. ("Reading your idea…"
      // itself is on screen twice there — the card and the caption strip.)
      expect(screen.getByText(/How does algorithmic accountability differ/)).toBeInTheDocument();

      // One step is 1150ms.
      act(() => {
        vi.advanceTimersByTime(1200);
      });
      expect(screen.getByText(/Topic Discovery/)).toBeInTheDocument();

      act(() => {
        vi.advanceTimersByTime(1200);
      });
      expect(screen.getByText(/Literature Review/)).toBeInTheDocument();
    });

    test("offers Replay", () => {
      vi.useFakeTimers();
      render(<ProductMock />);

      expect(screen.getByRole("button", { name: /replay/i })).toBeInTheDocument();
    });
  });
});
