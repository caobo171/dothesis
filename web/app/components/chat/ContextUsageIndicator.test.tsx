import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { LocaleProvider } from "@/app/lib/i18n/LocaleProvider";
import { ContextUsageIndicator, formatContextTokens } from "./ContextUsageIndicator";


function renderEn(contextTokens: number, compactAtTokens: number) {
  return render(
    <LocaleProvider initialLocale="en" hasCookie>
      <ContextUsageIndicator
        contextUsage={{ contextTokens, compactAtTokens }}
      />
    </LocaleProvider>,
  );
}


describe("ContextUsageIndicator", () => {
  test("shows context, remaining tokens, and progress to auto-compact", () => {
    renderEn(88_000, 170_000);

    expect(screen.getByText("Context 88K · compact in 82K · 52%")).toBeTruthy();
  });

  test("shows automatic compaction state at the threshold", () => {
    renderEn(170_000, 170_000);

    expect(screen.getByText("Context 170K · compacting automatically…")).toBeTruthy();
  });

  test("hides when no valid snapshot exists", () => {
    const { container } = renderEn(0, 170_000);

    expect(container).toBeEmptyDOMElement();
  });

  test("formats large values compactly", () => {
    expect(formatContextTokens(999)).toBe("999");
    expect(formatContextTokens(88_000)).toBe("88K");
    expect(formatContextTokens(1_200_000)).toBe("1.2M");
  });
});
