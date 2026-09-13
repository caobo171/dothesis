import { describe, expect, test } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { LocaleProvider } from "@/app/lib/i18n/LocaleProvider";
import { ContextSummaryCard } from "./ContextSummaryCard";

const SUMMARY =
  "## SESSION INTENT\n\nCải thiện và xuất lại luận văn\n\n## SUMMARY\n\n- M1: done\n- M3: in_progress";

function renderVi(text: string) {
  return render(
    <LocaleProvider initialLocale="vi" hasCookie>
      <ContextSummaryCard hint={{ widget_type: "context_summary", text }} />
    </LocaleProvider>,
  );
}

describe("ContextSummaryCard", () => {
  test("labels the compaction and keeps the note collapsed", () => {
    renderVi(SUMMARY);

    expect(screen.getByText("Đã tóm tắt hội thoại để tiếp tục")).toBeTruthy();
    // Collapsed: the note is not competing with the actual answer above it.
    expect(screen.queryByText(/SESSION INTENT/)).toBeNull();
    expect(screen.getByRole("button")).toHaveAttribute("aria-expanded", "false");
  });

  test("shows the note verbatim once opened", () => {
    renderVi(SUMMARY);
    fireEvent.click(screen.getByRole("button"));

    expect(screen.getByRole("button")).toHaveAttribute("aria-expanded", "true");
    // Verbatim — a student can only catch a summary that got a fact wrong by
    // reading what it actually says.
    expect(screen.getByText(/## SESSION INTENT/)).toBeTruthy();
    expect(screen.getByText(/M3: in_progress/)).toBeTruthy();
  });

  test("renders nothing when there is no summary text", () => {
    const { container } = renderVi("   ");
    expect(container.firstChild).toBeNull();
  });
});
