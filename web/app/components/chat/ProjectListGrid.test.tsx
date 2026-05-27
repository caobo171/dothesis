import { describe, expect, test, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../../../tests/setup";
import { ProjectListGrid } from "./ProjectListGrid";


// useRouter is used by ProjectListGrid to navigate after project creation.
// Stub it for unit tests so the component renders outside the App Router.
const _push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: _push, replace: vi.fn(), back: vi.fn() }),
}));


describe("ProjectListGrid", () => {
  test("renders project cards", async () => {
    server.use(
      http.get("/api/v1/projects", () => HttpResponse.json([
        { id: "p1", name: "Leadership Thesis", field: "Marketing", language: "en",
          citation_style: "apa", status: "draft", current_module: "M2",
          context_store: { m1_topic: { confirmed_at: "x" } },
          created_at: "2026-05-27", updated_at: "2026-05-27" },
      ])),
    );
    render(<ProjectListGrid />);
    await waitFor(() => expect(screen.getByText("Leadership Thesis")).toBeTruthy());
  });

  test("renders empty state when no projects", async () => {
    server.use(
      http.get("/api/v1/projects", () => HttpResponse.json([])),
    );
    render(<ProjectListGrid />);
    await waitFor(() => expect(screen.getByText(/no projects yet/i)).toBeTruthy());
  });

  test("clicking New project opens the modal (not window.prompt)", async () => {
    server.use(
      http.get("/api/v1/projects", () => HttpResponse.json([])),
    );
    render(<ProjectListGrid />);
    await waitFor(() => expect(screen.getByText(/no projects yet/i)).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /new project/i }));
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getByText(/create new project/i)).toBeTruthy();
  });

  test("creating a project navigates to its chat URL", async () => {
    server.use(
      http.get("/api/v1/projects", () => HttpResponse.json([])),
      http.post("/api/v1/projects", async ({ request }) => {
        const body = (await request.json()) as { name: string };
        return HttpResponse.json({ id: "p-new", name: body.name });
      }),
    );
    _push.mockClear();
    render(<ProjectListGrid />);
    await waitFor(() => expect(screen.getByText(/no projects yet/i)).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /new project/i }));
    fireEvent.change(screen.getByLabelText(/project name/i), { target: { value: "Brand new" } });
    fireEvent.click(screen.getByRole("button", { name: /^create$/i }));
    await waitFor(() => expect(_push).toHaveBeenCalledWith("/chat/projects/p-new"));
  });
});
