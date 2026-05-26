import { describe, expect, test } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { http } from "msw";
import { server } from "../../../../tests/setup";
import { streamResponse } from "../../../../tests/helpers/sseResponse";
import { useStream } from "./useStream";


describe("useStream", () => {
  test("parses single-line SSE event", async () => {
    server.use(
      http.post("/api/test", () => streamResponse([
        'data: {"type":"token","text":"hi"}\n\n',
        'data: {"type":"done"}\n\n',
      ])),
    );

    const { result } = renderHook(() => useStream());
    await act(async () => {
      await result.current.start("/api/test", { method: "POST" });
    });

    expect(result.current.state.events).toEqual([
      { type: "token", text: "hi" },
      { type: "done" },
    ]);
    expect(result.current.state.inflight).toBe(false);
  });

  test("handles partial chunks across reads", async () => {
    server.use(
      http.post("/api/test", () => streamResponse([
        'data: {"type":"tok',
        'en","text":"a"}\n\n',
        'data: {"type":"done"}\n\n',
      ])),
    );

    const { result } = renderHook(() => useStream());
    await act(async () => {
      await result.current.start("/api/test", { method: "POST" });
    });

    expect(result.current.state.events).toEqual([
      { type: "token", text: "a" },
      { type: "done" },
    ]);
  });

  test("malformed frame is silently skipped", async () => {
    server.use(
      http.post("/api/test", () => streamResponse([
        'data: not-json\n\n',
        'data: {"type":"token","text":"ok"}\n\n',
        'data: {"type":"done"}\n\n',
      ])),
    );

    const { result } = renderHook(() => useStream());
    await act(async () => {
      await result.current.start("/api/test", { method: "POST" });
    });

    expect(result.current.state.events).toEqual([
      { type: "token", text: "ok" },
      { type: "done" },
    ]);
  });

  test("HTTP error surfaces in state.error", async () => {
    server.use(
      http.post("/api/test", () => new Response(null, { status: 500 })),
    );

    const { result } = renderHook(() => useStream());
    await act(async () => {
      await result.current.start("/api/test", { method: "POST" });
    });

    expect(result.current.state.error).not.toBeNull();
    expect(result.current.state.inflight).toBe(false);
  });

  test("cancel aborts mid-stream", async () => {
    let resolveSecondChunk: () => void = () => {};
    const secondChunkPromise = new Promise<void>(r => (resolveSecondChunk = r));

    server.use(
      http.post("/api/test", () => {
        const stream = new ReadableStream({
          async start(controller) {
            const encoder = new TextEncoder();
            controller.enqueue(encoder.encode('data: {"type":"token","text":"a"}\n\n'));
            await secondChunkPromise;
            controller.enqueue(encoder.encode('data: {"type":"done"}\n\n'));
            controller.close();
          },
        });
        return new Response(stream, {
          headers: { "Content-Type": "text/event-stream" },
        });
      }),
    );

    const { result } = renderHook(() => useStream());
    act(() => {
      void result.current.start("/api/test", { method: "POST" });
    });
    // Wait for first event
    await waitFor(() => {
      expect(result.current.state.events.length).toBeGreaterThan(0);
    });

    act(() => result.current.cancel());
    expect(result.current.state.inflight).toBe(false);

    // Let the server finish — should NOT add more events
    resolveSecondChunk();
    await new Promise(r => setTimeout(r, 50));
    expect(result.current.state.events.find(e => e.type === "done")).toBeUndefined();
  });
});
