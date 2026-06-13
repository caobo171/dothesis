import { describe, expect, test } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { http } from "msw";
import { server } from "../../../../tests/setup";
import { streamResponse } from "../../../../tests/helpers/sseResponse";
import { useProjectState } from "./useProjectState";


describe("useProjectState", () => {
  test("reduces context_update events into a snapshot", async () => {
    server.use(
      http.post("/api/v1/threads/t1/state", () => streamResponse([
        'data: {"type":"context_update","patch":{"m1_topic":{"research_title":"X"}}}\n\n',
        'data: {"type":"context_update","patch":{"m2_literature":{"research_state_summary":"Y"}}}\n\n',
      ])),
    );

    const { result } = renderHook(() => useProjectState("t1"));
    await waitFor(() => {
      expect(result.current.latest.m1_topic).toEqual({ research_title: "X" });
    });
    expect(result.current.latest.m2_literature).toEqual({ research_state_summary: "Y" });
  });
});
