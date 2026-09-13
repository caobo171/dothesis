import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useChapterAutosave } from "../hooks/useChapterAutosave";


beforeEach(() => {
  vi.useFakeTimers();
  global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ prose: "x" }) });
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});


describe("useChapterAutosave", () => {
  it("debounces multiple onChange calls into one PATCH", async () => {
    const { result } = renderHook(() =>
      useChapterAutosave({ projectId: "p1", chapterName: "intro" })
    );
    act(() => { result.current.queue("first"); });
    act(() => { result.current.queue("second"); });
    act(() => { result.current.queue("third"); });
    expect(fetch).not.toHaveBeenCalled();
    await act(async () => { await vi.advanceTimersByTimeAsync(1100); });
    expect(fetch).toHaveBeenCalledTimes(1);
    const call = (fetch as any).mock.calls[0];
    // apiFetch prepends the API base; assert the path rather than an exact URL.
    expect(call[0]).toContain("/api/v1/projects/p1/m5/chapters/intro");
    expect(call[1].method).toBe("PATCH");
    expect(JSON.parse(call[1].body).prose).toBe("third");
  });

  it("exposes saving / lastSavedAt", async () => {
    const { result } = renderHook(() =>
      useChapterAutosave({ projectId: "p1", chapterName: "intro" })
    );
    act(() => { result.current.queue("x"); });
    // Advance past the debounce so flush() runs and calls fetch (which is a
    // pre-resolved mock). Then drain remaining microtasks via a no-op async
    // act so React commits the setSaving(false) state update before we assert.
    // waitFor hangs under vi.useFakeTimers() because its internal polling loop
    // uses jest.advanceTimersByTime which consumes the overallTimeoutTimer —
    // using act-based draining avoids that issue entirely.
    await act(async () => { await vi.advanceTimersByTimeAsync(1100); });
    await act(async () => {});
    expect(result.current.saving).toBe(false);
    expect(result.current.lastSavedAt).not.toBeNull();
  });

  it("retries 3x on network failure", async () => {
    let calls = 0;
    (global.fetch as any) = vi.fn().mockImplementation(() => {
      calls++;
      if (calls < 3) return Promise.reject(new Error("net"));
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });
    const { result } = renderHook(() =>
      useChapterAutosave({ projectId: "p1", chapterName: "intro" })
    );
    act(() => { result.current.queue("x"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(1100); });
    await act(async () => { await vi.advanceTimersByTimeAsync(250); });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(calls).toBe(3);
  });
});

// Mocks `global.fetch` like the tests above — apiFetch folds the auth token in,
// so the prose is read back out of the request body.
function _proseOf(call: any): string {
  return JSON.parse(call[1].body).prose;
}


describe("a save that fails", () => {
  function _failTwiceThenSucceed(failures: number) {
    let n = 0;
    global.fetch = vi.fn().mockImplementation(async () => {
      n += 1;
      if (n <= failures) throw new Error("network");
      return { ok: true, json: async () => ({ prose: "x" }) };
    });
  }

  it("keeps the prose so a retry can send it again", async () => {
    // `flush` clears the queue before the first attempt. After three failures
    // the text existed only in the in-memory document — a retry no-opped and a
    // reload lost it.
    _failTwiceThenSucceed(3);
    const { result } = renderHook(() =>
      useChapterAutosave({ projectId: "p1", chapterName: "intro" }));

    act(() => { result.current.queue("typed text"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });
    expect(result.current.error).toBeTruthy();

    // The retry sends the SAME prose rather than finding an empty queue.
    await act(async () => { await result.current.flush(); });
    const calls = (fetch as any).mock.calls;
    expect(_proseOf(calls.at(-1))).toBe("typed text");
    expect(result.current.error).toBeNull();
  });

  it("does not resurrect stale prose over something typed since", async () => {
    _failTwiceThenSucceed(3);
    const { result } = renderHook(() =>
      useChapterAutosave({ projectId: "p1", chapterName: "intro" }));

    act(() => { result.current.queue("old"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });
    act(() => { result.current.queue("new"); });   // typed while it was failing
    await act(async () => { await result.current.flush(); });

    expect(_proseOf((fetch as any).mock.calls.at(-1))).toBe("new");
  });
});
