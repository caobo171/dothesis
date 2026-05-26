import { describe, expect, test } from "vitest";
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
