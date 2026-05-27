import { describe, expect, it, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChatHeader } from "./ChatHeader";


describe("ChatHeader", () => {
  test("renders project + thread name", () => {
    render(<ChatHeader projectName="Leadership Thesis" threadName="Main" autoDraftButton={null} />);
    expect(screen.getByText("Leadership Thesis")).toBeTruthy();
    expect(screen.getByText("Main")).toBeTruthy();
  });

  test("renders auto-draft slot", () => {
    render(<ChatHeader projectName="X" threadName="Y" autoDraftButton={<button>Auto-draft</button>} />);
    expect(screen.getByRole("button", { name: /auto-draft/i })).toBeTruthy();
  });
});

describe("ChatHeader — open-editor button (SP6.5)", () => {
  it("does not show 'Open editor' when chapters are absent", () => {
    render(<ChatHeader projectName="X" threadName="Y" autoDraftButton={null} projectId="p1" hasChapters={false} />);
    expect(screen.queryByRole("link", { name: /open editor/i })).not.toBeInTheDocument();
  });

  it("shows 'Open editor' link to /chat/projects/{pid}/editor when chapters present", () => {
    render(<ChatHeader projectName="X" threadName="Y" autoDraftButton={null} projectId="p1" hasChapters={true} />);
    const link = screen.getByRole("link", { name: /open editor/i });
    expect(link).toHaveAttribute("href", "/chat/projects/p1/editor");
  });
});
