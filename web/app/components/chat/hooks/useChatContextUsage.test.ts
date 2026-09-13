import { describe, expect, test } from "vitest";

import { selectContextUsage } from "./useChat";


describe("selectContextUsage", () => {
  test("live done snapshot overrides the newest persisted assistant snapshot", () => {
    const result = selectContextUsage(
      [{
        id: 1,
        role: "assistant",
        content: "old",
        context_tokens: 40_000,
        compact_at_tokens: 170_000,
        created_at: "2026-09-12T00:00:00Z",
      }],
      [{
        type: "done",
        context_tokens: 88_000,
        compact_at_tokens: 170_000,
      }],
    );

    expect(result).toEqual({
      contextTokens: 88_000,
      compactAtTokens: 170_000,
    });
  });

  test("falls back to latest valid persisted assistant snapshot", () => {
    const result = selectContextUsage(
      [{
        id: 1,
        role: "assistant",
        content: "persisted",
        context_tokens: 40_000,
        compact_at_tokens: 170_000,
        created_at: "2026-09-12T00:00:00Z",
      }],
      [],
    );

    expect(result?.contextTokens).toBe(40_000);
  });
});
