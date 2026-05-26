import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../../../tests/setup";
import { AutoDraftModal } from "./AutoDraftModal";


describe("AutoDraftModal", () => {
  test("fetches estimate and renders it", async () => {
    server.use(
      http.get("/api/v1/projects/p1/runs/estimate", () =>
        HttpResponse.json({ estimated_tokens: 18500, credit_balance: 50000, sufficient_credit: true }),
      ),
    );
    render(
      <AutoDraftModal
        open={true}
        projectId="p1"
        defaultTopic="Leadership"
        onClose={() => {}}
        onConfirm={() => {}}
      />,
    );
    await waitFor(() => expect(screen.getByText(/18,500/)).toBeTruthy());
    expect(screen.getByText(/50,000/)).toBeTruthy();
  });

  test("confirm fires callback with topic", async () => {
    server.use(
      http.get("/api/v1/projects/p1/runs/estimate", () =>
        HttpResponse.json({ estimated_tokens: 100, credit_balance: 1000, sufficient_credit: true }),
      ),
    );
    const onConfirm = vi.fn();
    render(
      <AutoDraftModal open={true} projectId="p1" defaultTopic="seed" onClose={() => {}} onConfirm={onConfirm} />,
    );
    await waitFor(() => expect(screen.getByDisplayValue("seed")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /^start auto-draft$/i }));
    expect(onConfirm).toHaveBeenCalledWith("seed");
  });

  test("does not render when open=false", () => {
    render(<AutoDraftModal open={false} projectId="p1" defaultTopic="" onClose={() => {}} onConfirm={() => {}} />);
    expect(screen.queryByText(/start auto-draft/i)).toBeNull();
  });
});
