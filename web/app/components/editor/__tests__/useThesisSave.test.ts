/**
 * Saving is EXPLICIT and DOCUMENT-WIDE.
 *
 * It used to PATCH on a 1s debounce after every keystroke — a request per
 * sentence, per student, for as long as the tab was open — and the state lived
 * per chapter, which put five "Unsaved changes · Save" bars down a page the
 * student reads as one document.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useThesisSave } from "../hooks/useThesisSave";


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


describe("useThesisSave", () => {
  it("does not touch the server while the student types", async () => {
    const { result } = renderHook(() =>
      useThesisSave({ projectId: "p1" }));

    act(() => { result.current.track("intro", "first"); });
    act(() => { result.current.track("intro", "second"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });

    expect(fetch).not.toHaveBeenCalled();
    expect(result.current.dirty).toBe(true);
  });

  it("sends what is on screen when Save is pressed, once", async () => {
    const { result } = renderHook(() =>
      useThesisSave({ projectId: "p1" }));

    act(() => { result.current.track("intro", "first"); });
    act(() => { result.current.track("intro", "latest"); });
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
      useThesisSave({ projectId: "p1" }));
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
      useThesisSave({ projectId: "p1" }));
    act(() => { result.current.track("intro", "typed text"); });

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
      useThesisSave({ projectId: "p1" }));

    act(() => { result.current.track("intro", "old"); });
    let pending!: Promise<void>;
    act(() => { pending = result.current.save(); });
    act(() => { result.current.track("intro", "newer"); });
    await act(async () => { await pending; });

    // The newer text has not been sent, so the chapter is not clean.
    expect(result.current.dirty).toBe(true);
  });
});

describe("one Save for the whole document", () => {
  it("sends every chapter that changed, and only those", async () => {
    const { result } = renderHook(() => useThesisSave({ projectId: "p1" }));

    act(() => { result.current.track("intro", "intro text"); });
    act(() => { result.current.track("results", "results text"); });
    await act(async () => { await result.current.save(); });

    const calls = (fetch as any).mock.calls;
    expect(calls).toHaveLength(2);
    const byChapter = Object.fromEntries(
      calls.map((c: any) => [String(c[0]).split("/").pop(), _proseOf(c)]));
    expect(byChapter).toEqual({ intro: "intro text", results: "results text" });
    expect(result.current.dirty).toBe(false);
  });

  it("keeps only the chapter that failed in the queue", async () => {
    // A partial failure must not re-send the chapters that landed, and must not
    // report the document clean either.
    global.fetch = vi.fn().mockImplementation(async (url: string) => {
      if (String(url).endsWith("/results")) throw new Error("network");
      return { ok: true, json: async () => ({ prose: "x" }) };
    });

    const { result } = renderHook(() => useThesisSave({ projectId: "p1" }));
    act(() => { result.current.track("intro", "intro text"); });
    act(() => { result.current.track("results", "results text"); });

    let first!: Promise<void>;
    act(() => { first = result.current.save(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(20_000); await first; });

    expect(result.current.dirty).toBe(true);
    expect(result.current.error).toBeTruthy();

    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ prose: "x" }) });
    await act(async () => { await result.current.save(); });

    const retried = (fetch as any).mock.calls;
    expect(retried).toHaveLength(1);
    expect(String(retried[0][0])).toContain("/results");
    expect(result.current.dirty).toBe(false);
  });
});

describe("what has changed since the last save", () => {
  it("reports the before and after per chapter", async () => {
    const { result } = renderHook(() => useThesisSave({ projectId: "p1" }));
    act(() => { result.current.seed("intro", "Sự phát triển nhanh."); });
    act(() => { result.current.track("intro", "Sự phát triển rất nhanh."); });

    expect(result.current.changes()).toEqual([
      { chapter: "intro", before: "Sự phát triển nhanh.", after: "Sự phát triển rất nhanh." },
    ]);
  });

  it("typing something and undoing it is not an unsaved change", async () => {
    // TipTap also re-serialises on mount. Calling that "unsaved changes" trains
    // the student to ignore the warning that matters.
    const { result } = renderHook(() => useThesisSave({ projectId: "p1" }));
    act(() => { result.current.seed("intro", "original"); });
    act(() => { result.current.track("intro", "original typo"); });
    expect(result.current.dirty).toBe(true);

    act(() => { result.current.track("intro", "original"); });
    expect(result.current.dirty).toBe(false);
    expect(result.current.changes()).toEqual([]);
  });

  it("a saved chapter becomes the new baseline", async () => {
    const { result } = renderHook(() => useThesisSave({ projectId: "p1" }));
    act(() => { result.current.seed("intro", "v1"); });
    act(() => { result.current.track("intro", "v2"); });
    await act(async () => { await result.current.save(); });

    // Back to v1 is now itself a change, not a return to clean.
    act(() => { result.current.track("intro", "v1"); });
    expect(result.current.changes()).toEqual([
      { chapter: "intro", before: "v2", after: "v1" },
    ]);
  });
});
