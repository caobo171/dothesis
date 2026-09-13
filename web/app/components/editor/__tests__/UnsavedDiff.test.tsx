import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { LocaleProvider } from "@/app/lib/i18n/LocaleProvider";
import { UnsavedDiff } from "../UnsavedDiff";

function renderEn(changes: any[], props: any = {}) {
  return render(
    <LocaleProvider initialLocale="en" hasCookie>
      <UnsavedDiff changes={changes} onClose={() => {}} onSave={() => {}} {...props} />
    </LocaleProvider>,
  );
}

describe("UnsavedDiff", () => {
  test("marks what was added and what was removed", () => {
    renderEn([{
      chapter: "intro",
      before: "Sự phát triển nhanh của mạng xã hội.",
      after: "Sự phát triển rất nhanh của mạng xã hội.",
    }]);

    const added = document.querySelector("ins");
    expect(added?.textContent).toContain("rất");
    // The unchanged remainder is still shown, as context.
    expect(screen.getByTestId("diff-intro").textContent).toContain("mạng xã hội");
  });

  test("shows a deletion as a deletion, not as a rewrite", () => {
    renderEn([{ chapter: "intro", before: "một hai ba bốn", after: "một ba bốn" }]);
    expect(document.querySelector("del")?.textContent).toContain("hai");
  });

  test("lists every changed chapter", () => {
    renderEn([
      { chapter: "intro", before: "a", after: "ab" },
      { chapter: "results", before: "c", after: "cd" },
    ]);
    expect(screen.getByTestId("diff-intro")).toBeTruthy();
    expect(screen.getByTestId("diff-results")).toBeTruthy();
  });

  test("saving from here closes it — the diff is how you decide to save", () => {
    const onSave = vi.fn();
    const onClose = vi.fn();
    renderEn([{ chapter: "intro", before: "a", after: "ab" }], { onSave, onClose });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onSave).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  test("says so plainly when nothing actually differs", () => {
    renderEn([]);
    expect(screen.getByText(/nothing differs/i)).toBeTruthy();
  });
});
