import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { LocaleProvider } from "@/app/lib/i18n/LocaleProvider";
import { ChapterEditor } from "../ChapterEditor";


beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ name: "intro", prose: "Hello world.", pending_edits: [] }),
  }));
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});


describe("ChapterEditor — mount + save", () => {
  it("renders the chapter prose", async () => {
    render(
      <LocaleProvider initialLocale="en" hasCookie>
      <ChapterEditor
        projectId="p1"
        chapterName="intro"
        initialProse="Hello world."
        pendingEdits={[]}
        onPendingMutate={() => {}}
        onProseChange={() => {}}
        fontFamily="serif"
        fontSize={16}
        lineHeight={1.75}
        paraGap={14}
      />
      </LocaleProvider>
    );
    await waitFor(() => expect(screen.getByText(/Hello world/)).toBeInTheDocument());
  });

  it("renders an artifact preview but seeds the original export path", async () => {
    const onSeed = vi.fn();
    const original = "/tmp/orchestrator_scratch/model.png";
    const preview = "data:image/png;base64,iVBORw0KGgo=";
    render(
      <LocaleProvider initialLocale="en" hasCookie>
      <ChapterEditor
        projectId="p1"
        chapterName="methodology"
        initialProse={`**Figure 3.1**\n\n![Research model](${original})`}
        media={[{ source: original, preview_url: preview }]}
        pendingEdits={[]}
        onPendingMutate={() => {}}
        onProseChange={() => {}}
        onSeed={onSeed}
        fontFamily="serif"
        fontSize={16}
        lineHeight={1.75}
        paraGap={14}
      />
      </LocaleProvider>
    );
    await waitFor(() => expect(screen.getByRole("img", { name: "Research model" })).toHaveAttribute("src", preview));
    await waitFor(() => expect(onSeed).toHaveBeenCalled());
    expect(onSeed.mock.calls[0][0]).toContain(`](${original})`);
    expect(onSeed.mock.calls[0][0]).not.toContain(preview);
  });

  it("applies an accepted proposal to the mounted TipTap document and reconciles the parent queue", async () => {
    const onServerProse = vi.fn();
    (global.fetch as any) = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ name: "intro", prose: "New text.", document_fingerprint: "after", pending_edits: [] }),
    });
    render(
      <LocaleProvider initialLocale="en" hasCookie>
        <ChapterEditor projectId="p1" chapterName="intro" initialProse="Old text." pendingEdits={[{
          id: "e1", source: "paraphrase", oldText: "Old text.", newText: "New text.", from_offset: 0, to_offset: 9,
        }]} onPendingMutate={() => {}} onProseChange={() => {}} onServerProse={onServerProse}
          fontFamily="serif" fontSize={16} lineHeight={1.75} paraGap={14} />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByRole("button", { name: "Accept" })).toBeInTheDocument());
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Accept" })); });
    await waitFor(() => expect(screen.getAllByText("New text.").length).toBeGreaterThan(1));
    expect(onServerProse).toHaveBeenCalledWith("New text.", "after");
  });

  it("retries a proposal against its captured document revision", async () => {
    (global.fetch as any) = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    render(
      <LocaleProvider initialLocale="en" hasCookie>
        <ChapterEditor projectId="p1" chapterName="intro" initialProse="Old text." documentFingerprint="current-revision" pendingEdits={[{
          id: "e1", source: "paraphrase", oldText: "Old text.", newText: "New text.", from_offset: 0, to_offset: 9,
          metadata: { document_fingerprint: "proposal-revision" },
        }]} onPendingMutate={() => {}} onProseChange={() => {}}
          fontFamily="serif" fontSize={16} lineHeight={1.75} paraGap={14} />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByRole("button", { name: /Try again/i })).toBeInTheDocument());
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: /Try again/i })); });
    expect(JSON.parse((fetch as any).mock.calls[0][1].body)).toMatchObject({
      expected_document_fingerprint: "proposal-revision",
    });
  });
});
