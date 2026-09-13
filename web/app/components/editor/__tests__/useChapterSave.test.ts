/**
 * Saving is EXPLICIT. This used to PATCH on a 1s debounce after every
 * keystroke — a write per sentence, per student, for as long as the tab was
 * open. `track` now only records; `save` is the request.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useChapterSave } from "../hooks/useChapterSave";


beforeEach(() => {
  vi.useFakeTimers();
  global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ prose: "x" }) });
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function _proseOf(call: any): string {
  return JSON.parse(call[1].body).prose;
}


describe("useChapterSave", () => {
  it("does not touch the server while the student types", async () => {
    const { result } = renderHook(() =>
      useChapterSave({ projectId: "p1", chapterName: "intro" }));

    act(() => { result.current.track("first"); });
    act(() => { result.current.track("second"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });

    expect(fetch).not.toHaveBeenCalled();
    expect(result.current.dirty).toBe(true);
  });

  it("sends what is on screen when Save is pressed, once", async () => {
    const { result } = renderHook(() =>
      useChapterSave({ projectId: "p1", chapterName: "intro" }));

    act(() => { result.current.track("first"); });
    act(() => { result.current.track("latest"); });
    await act(async () => { await result.current.save(); });

    expect(fetch).toHaveBeenCalledTimes(1);
    const call = (fetch as any).mock.calls[0];
    expect(call[0]).toContain("/projects/p1/m5/chapters/intro");
    expect(call[1].method).toBe("PATCH");
    expect(_proseOf(call)).toBe("latest");
    expect(result.current.dirty).toBe(false);
    expect(result.current.lastSavedAt).toBeInstanceOf(Date);
  });

  it("saving with nothing to save does not hit the server", async () => {
    const { result } = renderHook(() =>
      useChapterSave({ projectId: "p1", chapterName: "intro" }));
    await act(async () => { await result.current.save(); });
    expect(fetch).not.toHaveBeenCalled();
  });

  it("stays dirty when the save fails, and keeps the prose for the retry", async () => {
    // Losing a save matters more now that saves are deliberate and further
    // apart: `save` clears the queue before the first attempt, so without
    // putting it back a retry would find nothing to send.
    let n = 0;
    global.fetch = vi.fn().mockImplementation(async () => {
      n += 1;
      if (n <= 3) throw new Error("network");
      return { ok: true, json: async () => ({ prose: "x" }) };
    });

    const { result } = renderHook(() =>
      useChapterSave({ projectId: "p1", chapterName: "intro" }));
    act(() => { result.current.track("typed text"); });

    // The retry backoff sleeps on setTimeout, so the fake clock has to run
    // while the save is in flight.
    let first!: Promise<void>;
    act(() => { first = result.current.save(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(20_000); await first; });

    expect(result.current.error).toBeTruthy();
    expect(result.current.dirty).toBe(true);

    await act(async () => { await result.current.save(); });
    expect(_proseOf((fetch as any).mock.calls.at(-1))).toBe("typed text");
    expect(result.current.error).toBeNull();
    expect(result.current.dirty).toBe(false);
  });

  it("stays dirty when something is typed while the save is in flight", async () => {
    const { result } = renderHook(() =>
      useChapterSave({ projectId: "p1", chapterName: "intro" }));

    act(() => { result.current.track("old"); });
    let pending!: Promise<void>;
    act(() => { pending = result.current.save(); });
    act(() => { result.current.track("newer"); });
    await act(async () => { await pending; });

    // The newer text has not been sent, so the chapter is not clean.
    expect(result.current.dirty).toBe(true);
  });
});
