import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { usePendingEdits } from "../hooks/usePendingEdits";


beforeEach(() => {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ name: "intro", prose: "x", pending_edits: [] }),
  });
});
afterEach(() => vi.restoreAllMocks());


describe("usePendingEdits", () => {
  it("acceptEdit hits the accept endpoint and revalidates", async () => {
    const { result } = renderHook(() =>
      usePendingEdits({ projectId: "p1", chapterName: "intro" })
    );
    await act(async () => { await result.current.acceptEdit("edit-1"); });
    const calls = (fetch as any).mock.calls.map((c: any[]) => c[0]);
    expect(calls).toContain("/api/v1/projects/p1/m5/chapters/intro/pending/edit-1/accept");
  });

  it("rejectEdit hits the reject endpoint", async () => {
    const { result } = renderHook(() =>
      usePendingEdits({ projectId: "p1", chapterName: "intro" })
    );
    await act(async () => { await result.current.rejectEdit("edit-2"); });
    const calls = (fetch as any).mock.calls.map((c: any[]) => c[0]);
    expect(calls).toContain("/api/v1/projects/p1/m5/chapters/intro/pending/edit-2/reject");
  });

  it("acceptEdit returns the conflict body on 409", async () => {
    (global.fetch as any) = vi.fn().mockResolvedValue({
      ok: false, status: 409,
      json: async () => ({ detail: { error: { code: "stale_offsets", edit_id: "edit-1" } } }),
    });
    const { result } = renderHook(() =>
      usePendingEdits({ projectId: "p1", chapterName: "intro" })
    );
    const res = await result.current.acceptEdit("edit-1");
    expect(res.conflict).toBe(true);
  });
});
