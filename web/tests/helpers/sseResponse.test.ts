import { describe, expect, test } from "vitest";
import { streamResponse } from "./sseResponse";

describe("streamResponse", () => {
  test("returns text/event-stream response with chunks", async () => {
    const res = streamResponse([
      'data: {"type":"token","text":"hi"}\n\n',
      'data: {"type":"done"}\n\n',
    ]);
    expect(res.headers.get("Content-Type")).toBe("text/event-stream");
    const text = await res.text();
    expect(text).toContain('"token"');
    expect(text).toContain('"done"');
  });
});
