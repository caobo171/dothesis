import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { ChapterEditor } from "../ChapterEditor";


beforeEach(() => {
  vi.useFakeTimers();
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ name: "intro", prose: "Hello world.", pending_edits: [] }),
  });
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});


describe("ChapterEditor — mount + autosave", () => {
  it("renders the chapter prose", async () => {
    render(
      <ChapterEditor
        projectId="p1"
        chapterName="intro"
        initialProse="Hello world."
        pendingEdits={[]}
        onPendingMutate={() => {}}
        onDirty={() => {}}
        fontFamily="serif"
        fontSize={16}
      />
    );
    await waitFor(() => expect(screen.getByText(/Hello world/)).toBeInTheDocument());
  });
});
