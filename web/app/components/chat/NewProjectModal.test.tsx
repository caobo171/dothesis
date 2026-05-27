import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../../../tests/setup";
import { NewProjectModal } from "./NewProjectModal";


describe("NewProjectModal", () => {
  test("does not render when open=false", () => {
    render(<NewProjectModal open={false} onClose={() => {}} onCreated={() => {}} />);
    expect(screen.queryByText(/create new project/i)).toBeNull();
  });

  test("Create is disabled while name is empty", () => {
    render(<NewProjectModal open={true} onClose={() => {}} onCreated={() => {}} />);
    const createBtn = screen.getByRole("button", { name: /^create$/i });
    expect(createBtn).toBeDisabled();
  });

  test("POSTs to /projects + calls onCreated with returned project", async () => {
    server.use(
      http.post("/api/v1/projects", async ({ request }) => {
        const body = (await request.json()) as { name: string };
        return HttpResponse.json({ id: "p-new", name: body.name });
      }),
    );
    const onCreated = vi.fn();
    render(<NewProjectModal open={true} onClose={() => {}} onCreated={onCreated} />);
    const input = screen.getByLabelText(/project name/i);
    fireEvent.change(input, { target: { value: "Algorithmic Accountability" } });
    fireEvent.click(screen.getByRole("button", { name: /^create$/i }));
    await waitFor(() =>
      expect(onCreated).toHaveBeenCalledWith({ id: "p-new", name: "Algorithmic Accountability" }),
    );
  });

  test("trims whitespace before submitting", async () => {
    server.use(
      http.post("/api/v1/projects", async ({ request }) => {
        const body = (await request.json()) as { name: string };
        return HttpResponse.json({ id: "p-new", name: body.name });
      }),
    );
    const onCreated = vi.fn();
    render(<NewProjectModal open={true} onClose={() => {}} onCreated={onCreated} />);
    fireEvent.change(screen.getByLabelText(/project name/i), {
      target: { value: "  Padded Name  " },
    });
    fireEvent.click(screen.getByRole("button", { name: /^create$/i }));
    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    expect(onCreated.mock.calls[0][0].name).toBe("Padded Name");
  });

  test("shows error if POST fails", async () => {
    server.use(
      http.post("/api/v1/projects", () =>
        HttpResponse.json({ detail: { error: { code: "rate_limited" } } }, { status: 429 }),
      ),
    );
    const onCreated = vi.fn();
    render(<NewProjectModal open={true} onClose={() => {}} onCreated={onCreated} />);
    fireEvent.change(screen.getByLabelText(/project name/i), { target: { value: "X" } });
    fireEvent.click(screen.getByRole("button", { name: /^create$/i }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/rate_limited/i));
    expect(onCreated).not.toHaveBeenCalled();
  });

  test("Enter key submits the form", async () => {
    server.use(
      http.post("/api/v1/projects", async ({ request }) => {
        const body = (await request.json()) as { name: string };
        return HttpResponse.json({ id: "p-new", name: body.name });
      }),
    );
    const onCreated = vi.fn();
    render(<NewProjectModal open={true} onClose={() => {}} onCreated={onCreated} />);
    const input = screen.getByLabelText(/project name/i);
    fireEvent.change(input, { target: { value: "Enter test" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(onCreated).toHaveBeenCalled());
  });

  test("Cancel button fires onClose", () => {
    const onClose = vi.fn();
    render(<NewProjectModal open={true} onClose={onClose} onCreated={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
