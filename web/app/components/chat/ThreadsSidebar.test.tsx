import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ThreadsSidebar } from "./ThreadsSidebar";


const _threads = [
  { id: "t1", project_id: "p1", name: "Main", status: "active", langgraph_thread_id: "lg-1", created_at: "2026-05-27", last_active_at: "2026-05-27" },
  { id: "t2", project_id: "p1", name: "Alt", status: "active", langgraph_thread_id: "lg-2", created_at: "2026-05-27", last_active_at: "2026-05-27" },
];


describe("ThreadsSidebar", () => {
  test("lists all threads", () => {
    render(<ThreadsSidebar threads={_threads} currentThreadId="t1" onSelectThread={() => {}} onCreateThread={() => {}} />);
    expect(screen.getByText("Main")).toBeTruthy();
    expect(screen.getByText("Alt")).toBeTruthy();
  });

  test("highlights current thread", () => {
    render(<ThreadsSidebar threads={_threads} currentThreadId="t1" onSelectThread={() => {}} onCreateThread={() => {}} />);
    const mainItem = screen.getByText("Main").closest("button");
    expect(mainItem).toHaveClass("bg-primary-50");
  });

  test("click selects thread", () => {
    const onSelect = vi.fn();
    render(<ThreadsSidebar threads={_threads} currentThreadId="t1" onSelectThread={onSelect} onCreateThread={() => {}} />);
    fireEvent.click(screen.getByText("Alt").closest("button")!);
    expect(onSelect).toHaveBeenCalledWith("t2");
  });

  test("new thread button fires callback", () => {
    const onCreate = vi.fn();
    render(<ThreadsSidebar threads={_threads} currentThreadId="t1" onSelectThread={() => {}} onCreateThread={onCreate} />);
    fireEvent.click(screen.getByRole("button", { name: /new thread/i }));
    expect(onCreate).toHaveBeenCalled();
  });
});
