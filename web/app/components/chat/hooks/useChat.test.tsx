import { describe, expect, test } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../../../../tests/setup";
import { streamResponse } from "../../../../tests/helpers/sseResponse";
import { SWRConfig } from "swr";
import { ReactNode } from "react";
import { useChat } from "./useChat";


const wrapper = ({ children }: { children: ReactNode }) => (
  <SWRConfig value={{ dedupingInterval: 0, provider: () => new Map() }}>{children}</SWRConfig>
);


describe("useChat", () => {
  test("loads existing messages via SWR", async () => {
    server.use(
      http.get("/api/v1/threads/t1/messages", () => HttpResponse.json([
        { id: 1, role: "user", content: "hello", created_at: "2026-05-27T00:00:00Z" },
        { id: 2, role: "assistant", content: "hi", created_at: "2026-05-27T00:00:01Z" },
      ])),
    );

    const { result } = renderHook(() => useChat("t1"), { wrapper });
    await waitFor(() => expect(result.current.messages.length).toBe(2));
    expect(result.current.messages[0].content).toBe("hello");
  });

  test("send() optimistically appends user message and streams reply", async () => {
    server.use(
      http.get("/api/v1/threads/t1/messages", () => HttpResponse.json([])),
      http.post("/api/v1/threads/t1/messages", () => streamResponse([
        'data: {"type":"token","text":"reply"}\n\n',
        'data: {"type":"done"}\n\n',
      ])),
    );

    const { result } = renderHook(() => useChat("t1"), { wrapper });
    await waitFor(() => expect(result.current.messages).toEqual([]));

    await act(async () => {
      await result.current.send("hello world");
    });

    expect(result.current.streamingText).toBe("reply");
  });

  test("collects tool_calls SSE event into streamingToolCalls", async () => {
    server.use(
      http.get("/api/v1/threads/t1/messages", () => HttpResponse.json([])),
      http.post("/api/v1/threads/t1/messages", () => streamResponse([
        'data: {"type":"token","text":"Pick a field"}\n\n',
        'data: {"type":"tool_calls","payload":{"widget_type":"card_grid","field_name":"field","title":"Pick","options":[],"columns":3}}\n\n',
        'data: {"type":"done"}\n\n',
      ])),
    );

    const { result } = renderHook(() => useChat("t1"), { wrapper });
    await waitFor(() => expect(result.current.messages).toEqual([]));

    await act(async () => {
      await result.current.send("hello");
    });

    expect(result.current.streamingToolCalls).toMatchObject({
      widget_type: "card_grid",
      field_name: "field",
    });
  });
});
