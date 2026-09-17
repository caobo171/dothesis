import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { LocaleProvider } from "@/app/lib/i18n/LocaleProvider";
import { ChapterEditor, syncChapterForInlineAction } from "../ChapterEditor";


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
  it("anchors a claim-review suggestion in the prose without changing saved markdown", async () => {
    const onProseChange = vi.fn();
    const onClaimDecision = vi.fn().mockResolvedValue(undefined);
    const { container } = render(
      <LocaleProvider initialLocale="vi" hasCookie>
        <ChapterEditor projectId="p1" chapterName="intro" initialProse="Trust affects travel." pendingEdits={[]}
          claimSuggestions={[{
            id: "claim-1", chapter: "intro", anchor: { from_offset: 0, to_offset: 21, old_text: "Trust affects travel." },
            classification: "citation_opportunity", rationale_vi: "Nguồn hỗ trợ trực tiếp.",
            proposed_text: "Trust affects travel (Lee, 2024).", source: { id: "s1", title: "Travel trust", authors: ["Lee"], year: 2024 },
            evidence: { kind: "abstract", text: "Evidence", relation: "supports" }, status: "pending", actionable: true,
          }]}
          onClaimDecision={onClaimDecision} onPendingMutate={() => {}} onProseChange={onProseChange}
          fontFamily="serif" fontSize={16} lineHeight={1.75} paraGap={14} />
      </LocaleProvider>,
    );
    await waitFor(() => expect(container.querySelector(".claim-review-mark")).toHaveAttribute("data-claim-suggestion-id", "claim-1"));
    expect(container.querySelector(".claim-review-mark")).toHaveTextContent("Trust affects travel.");
    expect(onProseChange).not.toHaveBeenCalled();
  });

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

  it("refreshes an outdated fingerprint before creating an inline AI proposal", async () => {
    const stale = { ok: false, status: 409, json: async () => ({ detail: { error: { code: "stale_document" } } }) };
    (global.fetch as any) = vi.fn()
      .mockResolvedValueOnce(stale)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ intro: { prose: "Trust affects travel.", document_fingerprint: "fresh" } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    const result = await syncChapterForInlineAction({ projectId: "p1", chapterName: "intro", prose: "Trust affects travel.", fingerprint: "old" });
    expect(result.document_fingerprint).toBe("fresh");
    expect((global.fetch as any).mock.calls).toHaveLength(2);
  });

  it("keeps a real server prose conflict closed and explains that reload is required", async () => {
    const stale = { ok: false, status: 409, json: async () => ({ detail: { error: { code: "stale_document" } } }) };
    (global.fetch as any) = vi.fn()
      .mockResolvedValueOnce(stale)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ intro: { prose: "Newer server prose.", document_fingerprint: "fresh" } }) });
    await expect(syncChapterForInlineAction({ projectId: "p1", chapterName: "intro", prose: "Local prose.", fingerprint: "old" }))
      .rejects.toThrow(/tải lại chương/i);
  });
});
