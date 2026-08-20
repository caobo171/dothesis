import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AutoThesisButton } from "./AutoThesisButton";


describe("AutoThesisButton", () => {
  test.each([
    [null,        /^auto thesis$/i],
    ["queued",    /^auto thesis$/i],
    ["running",   /đang viết/i],
    ["paused",    /^resume$/i],
    ["done",      /done · download/i],
    ["failed",    /failed · retry/i],
    ["canceled",  /^auto thesis$/i],
  ])("status=%s renders correct label", (status, pattern) => {
    render(<AutoThesisButton runStatus={status as never} onClick={() => {}} />);
    expect(screen.getByRole("button").textContent).toMatch(pattern);
  });

  test("onClick fires", () => {
    const onClick = vi.fn();
    render(<AutoThesisButton runStatus={null} onClick={onClick} />);
    fireEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalled();
  });
});
