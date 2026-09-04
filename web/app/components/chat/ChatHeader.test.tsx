import { describe, expect, it, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChatHeader } from "./ChatHeader";
import { LocaleProvider } from "../../lib/i18n/LocaleProvider";

// ChatHeader calls useT(), which throws outside a LocaleProvider — every test
// here was failing on that before reaching an assertion. Pin to "en".
function renderHeader(ui: React.ReactElement) {
  return render(<LocaleProvider initialLocale="en" hasCookie>{ui}</LocaleProvider>);
}


describe("ChatHeader", () => {
  test("renders project + thread name", () => {
    renderHeader(<ChatHeader projectName="Leadership Thesis" threadName="Main" />);
    // Rendered as one combined span, "<project> · <thread>".
    expect(screen.getByText("Leadership Thesis · Main")).toBeTruthy();
  });

  test("no longer owns Quick actions — it moved to the composer", () => {
    // Auto Thesis + export/history/notifications used to hang off a Quick
    // actions menu in the header; they now live in QuickActionsMenu, rendered
    // by ChatInput. The header must not resurrect a copy.
    renderHeader(<ChatHeader projectName="X" threadName="Y" />);
    expect(screen.queryByRole("button", { name: /quick actions/i })).not.toBeInTheDocument();
  });
});

describe("ChatHeader — open-editor button (SP6.5)", () => {
  it("does not show 'Open editor' when chapters are absent", () => {
    renderHeader(<ChatHeader projectName="X" threadName="Y" projectId="p1" hasChapters={false} />);
    expect(screen.queryByRole("link", { name: /open editor/i })).not.toBeInTheDocument();
  });

  it("shows 'Open editor' link to /chat/projects/{pid}/editor when chapters present", () => {
    renderHeader(<ChatHeader projectName="X" threadName="Y" projectId="p1" hasChapters={true} />);
    const link = screen.getByRole("link", { name: /open editor/i });
    expect(link).toHaveAttribute("href", "/chat/projects/p1/editor");
  });
});
