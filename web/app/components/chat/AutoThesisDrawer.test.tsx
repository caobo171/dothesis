import { describe, expect, test, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../../../tests/setup";
import { streamResponse } from "../../../tests/helpers/sseResponse";
import { AutoThesisDrawer } from "./AutoThesisDrawer";


describe("AutoThesisDrawer", () => {
  test("renders module progress from events", async () => {
    server.use(
      http.post("*/api/v1/runs/r1", () => HttpResponse.json({
        id: "r1", project_id: "p1", status: "running", phase: null, progress: 0,
        mode: "auto", started_at: "2026-05-27T00:00:00Z", finished_at: null, error_text: null,
        events_url: "/api/v1/runs/r1/events",
      })),
      http.get("/api/v1/runs/r1/events", () => streamResponse([
        'data: {"type":"activity","module":"M1","text":"started"}\n\n',
        'data: {"type":"module_complete","module":"M1"}\n\n',
        'data: {"type":"activity","module":"M2","text":"scouting"}\n\n',
      ])),
    );

    render(<AutoThesisDrawer runId="r1" onClose={() => {}} />);

    await waitFor(() => {
      expect(screen.getByTestId("dot-M1")).toHaveClass("bg-[var(--ok-fg)]");
    });
    expect(screen.getByTestId("dot-M2")).toHaveClass("bg-primary-600");
  });

  test("close button fires onClose", async () => {
    server.use(
      http.post("*/api/v1/runs/r2", () => HttpResponse.json({ id: "r2", status: "running" })),
      http.get("/api/v1/runs/r2/events", () => streamResponse(['data: {"type":"done"}\n\n'])),
    );
    const onClose = vi.fn();
    render(<AutoThesisDrawer runId="r2" onClose={onClose} />);
    await waitFor(() => screen.getByLabelText(/close drawer/i));
    fireEvent.click(screen.getByLabelText(/close drawer/i));
    expect(onClose).toHaveBeenCalled();
  });
});
