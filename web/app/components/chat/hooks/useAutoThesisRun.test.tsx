import { describe, expect, test } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { http } from "msw";
import { server } from "../../../../tests/setup";
import { streamResponse } from "../../../../tests/helpers/sseResponse";
import { useAutoThesisRun } from "./useAutoThesisRun";


describe("useAutoThesisRun", () => {
  test("subscribes to /runs/{rid}/events when runId set", async () => {
    server.use(
      http.get("/api/v1/runs/r1/events", () => streamResponse([
        'data: {"type":"activity","module":"M1","text":"started"}\n\n',
        'data: {"type":"module_complete","module":"M1"}\n\n',
        'data: {"type":"job_done"}\n\n',
      ])),
    );

    const { result } = renderHook(() => useAutoThesisRun("r1"));
    await waitFor(() => {
      expect(result.current.events.some(e => e.type === "job_done")).toBe(true);
    });
    const completes = result.current.events.filter(e => e.type === "module_complete");
    expect(completes.length).toBe(1);
  });

  test("no run id → no fetch", () => {
    const { result } = renderHook(() => useAutoThesisRun(null));
    expect(result.current.events).toEqual([]);
  });
});
