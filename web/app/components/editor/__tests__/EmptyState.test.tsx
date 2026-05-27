import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { EmptyState } from "../EmptyState";


describe("EmptyState", () => {
  it("renders the explanation copy", () => {
    render(<EmptyState projectId="abc" />);
    expect(screen.getByText(/M5 hasn't drafted/i)).toBeInTheDocument();
  });

  it("links back to the chat", () => {
    render(<EmptyState projectId="abc" />);
    const link = screen.getByRole("link", { name: /open chat/i });
    expect(link).toHaveAttribute("href", "/chat/projects/abc");
  });
});
