import { describe, expect, test } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../../../tests/setup";
import { streamResponse } from "../../../tests/helpers/sseResponse";
import { ChatPane } from "./ChatPane";


describe("AutoThesis integration", () => {
  test("click button → modal → confirm → drawer → done", async () => {
    // runStatus tracks state across handler calls; starts at null (no active run)
    let runStatus: "running" | "done" | null = null;
    server.use(
      http.post("*/api/v1/projects/p1", () => HttpResponse.json({
        name: "T", context_store: { m1_topic: { research_title: "Leadership" } },
      })),
      http.post("*/api/v1/threads/t1", () => HttpResponse.json({ name: "Main" })),
      http.post("*/api/v1/threads/t1/messages/list", () => HttpResponse.json([])),
      http.post("*/api/v1/projects/p1/runs/list", () => HttpResponse.json({
        // Return the run object whenever we have an active runStatus
        run: runStatus ? { id: "r1", status: runStatus } : null,
      })),
      http.post("*/api/v1/projects/p1/runs/estimate", () => HttpResponse.json({
        estimated_tokens: 20000, credit_balance: 100000, sufficient_credit: true,
      })),
      http.post("*/api/v1/projects/p1/runs", () => {
        // POST creates the run and sets status to running
        runStatus = "running";
        return HttpResponse.json({ run_id: "r1", status: "running" });
      }),
      http.post("*/api/v1/runs/r1", () => HttpResponse.json({
        id: "r1", status: runStatus ?? "running", mode: "auto",
      })),
      http.get("/api/v1/runs/r1/events", () => streamResponse([
        'data: {"type":"activity","module":"M1","text":"start"}\n\n',
        'data: {"type":"module_complete","module":"M1"}\n\n',
        'data: {"type":"job_done","exports":{"docx":"s3://b/thesis.docx","pdf":"s3://b/thesis.pdf"}}\n\n',
      ])),
    );

    render(<ChatPane projectId="p1" threadId="t1" />);
    await waitFor(() => screen.getByRole("button", { name: /^auto thesis$/i }));

    // Click the trigger → opens the modal, whose confirm button carries the
    // SAME "Auto Thesis" label. Every query below is scoped to the dialog so
    // the two can never be confused for each other.
    fireEvent.click(screen.getByRole("button", { name: /^auto thesis$/i }));
    await waitFor(() => screen.getByRole("dialog"));

    // Modal has pre-filled topic + estimate
    await waitFor(() => expect(screen.getByDisplayValue("Leadership")).toBeTruthy());

    // Wait for estimate to load so the confirm button is enabled
    const dialog = screen.getByRole("dialog");
    await waitFor(() => expect(
      within(dialog).getByRole("button", { name: /^auto thesis$/i })).not.toBeDisabled());

    // Confirm
    fireEvent.click(within(dialog).getByRole("button", { name: /^auto thesis$/i }));

    // Drawer opens; module badge turns green after module_complete event
    // (design-token class from the 2026-06-10 DoThesis.html restyle)
    await waitFor(() => screen.getByText(/run r1/i), { timeout: 5000 });
    await waitFor(() => {
      expect(screen.getByTestId("dot-M1")).toHaveClass("bg-[var(--ok-fg)]");
    }, { timeout: 5000 });

    // After job_done, download links appear
    await waitFor(() => expect(screen.getByText(/download docx/i)).toBeTruthy(), { timeout: 5000 });
  });
});
