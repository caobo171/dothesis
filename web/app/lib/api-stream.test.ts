import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./tokenStore", () => ({
  tokenStore: { get: () => "test-token", clear: vi.fn() },
}));

import { apiPostStream } from "./api";

function sseResponse(frames: string[]) {
  const encoder = new TextEncoder();
  return new Response(new ReadableStream({
    start(controller) {
      for (const frame of frames) controller.enqueue(encoder.encode(frame));
      controller.close();
    },
  }), { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

describe("apiPostStream", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("delivers token events across network chunk boundaries and returns done", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse([
      'data: {"type":"token","text":"Hello"}\n',
      '\ndata: {"type":"token","text":" world"}\n\n',
      'data: {"type":"done","edit":{"id":"e1"}}\n\n',
    ])));
    const events: any[] = [];
    const terminal: any = await apiPostStream("/rewrite", { from_offset: 0 }, event => events.push(event));

    expect(events.map(event => event.type)).toEqual(["token", "token", "done"]);
    expect(events.filter(event => event.type === "token").map(event => event.text).join("")).toBe("Hello world");
    expect(terminal.edit.id).toBe("e1");
    expect(JSON.parse((fetch as any).mock.calls[0][1].body).access_token).toBe("test-token");
  });

  it("surfaces a terminal SSE error instead of accepting partial output", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse([
      'data: {"type":"token","text":"Partial"}\n\n',
      'data: {"type":"error","message":"Failed safely"}\n\n',
    ])));
    await expect(apiPostStream("/rewrite", {}, vi.fn())).rejects.toThrow("Failed safely");
  });
});
