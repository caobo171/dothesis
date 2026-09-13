/**
 * M5Body's "N/total chapters written" progress line.
 *
 * Regression: the denominator was a hardcoded `6`, a leftover from the
 * six-chapter model. Once all five canonical chapters exist (M5_CHAPTER_ORDER
 * in orchestrator/tools/m5_writing.py), a finished thesis read "5/6" —
 * telling the student their thesis was still missing a chapter it does not
 * have. The denominator must come from CHAPTER_ORDER (the same list the
 * outline rail renders), not a literal number, so it cannot drift again.
 */
import type { ReactElement } from "react";
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { LocaleProvider } from "@/app/lib/i18n/LocaleProvider";
import { M5Body } from "./ModuleSlices";
import { CHAPTER_ORDER } from "../editor/OutlineRail";

// The progress line comes from the catalogue now, so M5Body needs a provider;
// "en" pins it to the English copy these assertions are written against.
function renderEn(ui: ReactElement) {
  return render(<LocaleProvider initialLocale="en" hasCookie>{ui}</LocaleProvider>);
}

describe("M5Body chapter progress", () => {
  test("denominator matches the canonical five-chapter count, not a stale six", () => {
    const chapters = Object.fromEntries(
      CHAPTER_ORDER.map(({ name }) => [name, { prose: "…" }])
    );
    renderEn(<M5Body data={{ chapters }} />);
    expect(screen.getByText(`${CHAPTER_ORDER.length}/${CHAPTER_ORDER.length} chapters written`)).toBeInTheDocument();
    expect(screen.queryByText(/\/6 chapters written/)).not.toBeInTheDocument();
  });

  test("a partial draft counts correctly against the five-chapter total", () => {
    renderEn(<M5Body data={{ chapters: { intro: { prose: "…" }, conclusion: { prose: "…" } } }} />);
    expect(screen.getByText("2/5 chapters written")).toBeInTheDocument();
  });
});
