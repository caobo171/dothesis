import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AutoDraftButton } from "./AutoDraftButton";


describe("AutoDraftButton", () => {
  test.each([
    [null,        /^auto-draft$/i],
    ["queued",    /^auto-draft$/i],
    ["running",   /^auto-drafting/i],
    ["paused",    /^resume$/i],
    ["done",      /done · download/i],
    ["failed",    /failed · retry/i],
    ["canceled",  /^auto-draft$/i],
  ])("status=%s renders correct label", (status, pattern) => {
    render(<AutoDraftButton runStatus={status as never} onClick={() => {}} />);
    expect(screen.getByRole("button").textContent).toMatch(pattern);
  });

  test("onClick fires", () => {
    const onClick = vi.fn();
    render(<AutoDraftButton runStatus={null} onClick={onClick} />);
    fireEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalled();
  });
});
