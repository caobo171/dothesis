import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { WorkflowSidebar } from "./WorkflowSidebar";
import { LocaleProvider } from "../../lib/i18n/LocaleProvider";

const THREADS = [
  { id: "t1", name: "Main", status: "active" },
  { id: "t2", name: "Chương 4 rewrite", status: "active" },
] as never[];

const renderRail = (props: Partial<Parameters<typeof WorkflowSidebar>[0]> = {}) =>
  render(
    <LocaleProvider initialLocale="en" hasCookie>
      <WorkflowSidebar projectName="Untitled thesis" threads={THREADS}
                       onNewThread={vi.fn()} onSelectThread={vi.fn()} {...props} />
    </LocaleProvider>,
  );

describe("WorkflowSidebar", () => {
  test("shows the conversations when nothing is running", () => {
    renderRail();
    expect(screen.getByText("Main")).toBeTruthy();
    expect(screen.getByRole("button", { name: /new thread/i })).toBeTruthy();
  });

  // In an auto-mode project the run screen owns the workspace, so none of this
  // is actionable: the list holds one thread, and "New conversation" invites
  // the student to start a second one alongside a job whose entire premise is
  // that nobody types anything.
  test("hides the conversations when the workspace belongs to a run", () => {
    renderRail({ hideThreads: true });
    expect(screen.queryByText("Main")).toBeNull();
    expect(screen.queryByRole("button", { name: /new thread/i })).toBeNull();
  });

  test("keeps the way out of the project", () => {
    // Hiding the list must not strand anyone: the project chip and the home
    // link are how you leave, and neither is part of what is noisy here.
    renderRail({ hideThreads: true });
    expect(screen.getByText("Untitled thesis")).toBeTruthy();
    expect(screen.getByRole("link")).toBeTruthy();
  });

  test("keeps the credits footer", () => {
    renderRail({ hideThreads: true, projectCredits: 3734 });
    expect(screen.getByText("3,734")).toBeTruthy();
  });
});
