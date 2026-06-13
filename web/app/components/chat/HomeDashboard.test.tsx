import { describe, expect, test, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { SWRConfig } from "swr";
import { http, HttpResponse } from "msw";
import { server } from "../../../tests/setup";
import { HomeDashboard } from "./HomeDashboard";


// Isolated SWR cache per render — without it the useMe() result from one
// test (e.g. the default credit:0 stub) is served from the module-level
// cache in later tests. Same pattern as ChatPane.test.tsx.
function renderDashboard() {
  return render(
    <SWRConfig value={{ dedupingInterval: 0, provider: () => new Map() }}>
      <HomeDashboard />
    </SWRConfig>,
  );
}


// useRouter is used by HomeDashboard to navigate after project creation.
// Stub it for unit tests so the component renders outside the App Router.
const _push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: _push, replace: vi.fn(), back: vi.fn() }),
}));


// A realistic ProjectOut payload: module_status drives the card's module bar
// and the needs-review tag; context_store.confirmed_at is the legacy fallback.
const PROJECT = {
  id: "p1",
  name: "Leadership Thesis",
  field: "Marketing",
  language: "en",
  citation_style: "apa",
  status: "draft",
  current_module: "M2",
  focus: "M2",
  module_status: { M1: "done", M2: "in_progress", M3: "needs_review" },
  context_store: { m1_topic: { confirmed_at: "x" } },
  created_at: "2026-05-27",
  updated_at: "2026-05-27",
};


describe("HomeDashboard", () => {
  test("renders project cards with module bar and review tag", async () => {
    server.use(
      http.post("*/api/v1/projects/list", () => HttpResponse.json([PROJECT])),
    );
    renderDashboard();
    // The name also appears in the hero subtitle and activity timeline —
    // scope to the card's h3 heading.
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Leadership Thesis" })).toBeTruthy());
    // Module bar: M3 carries the needs_review flag → review tag + stat tile
    expect(screen.getAllByText(/needs review/i).length).toBeGreaterThan(0);
    // Hero resume CTA points at the most recently updated project
    expect(
      (screen.getByRole("link", { name: /resume current thesis/i }) as HTMLAnchorElement).href,
    ).toContain("/chat/projects/p1");
  });

  test("renders empty state when no projects", async () => {
    server.use(
      http.post("*/api/v1/projects/list", () => HttpResponse.json([])),
    );
    renderDashboard();
    await waitFor(() => expect(screen.getByText(/no projects yet/i)).toBeTruthy());
    // No project to resume → hero offers only the start CTA
    expect(screen.queryByRole("link", { name: /resume current thesis/i })).toBeNull();
  });

  test("clicking New thesis opens the modal (not window.prompt)", async () => {
    server.use(
      http.post("*/api/v1/projects/list", () => HttpResponse.json([])),
    );
    renderDashboard();
    await waitFor(() => expect(screen.getByText(/no projects yet/i)).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /^new thesis$/i }));
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getByText(/create new project/i)).toBeTruthy();
  });

  test("creating a project navigates to its chat URL", async () => {
    server.use(
      http.post("*/api/v1/projects/list", () => HttpResponse.json([])),
      http.post("*/api/v1/projects", async ({ request }) => {
        const body = (await request.json()) as { name: string };
        return HttpResponse.json({ id: "p-new", name: body.name });
      }),
    );
    _push.mockClear();
    renderDashboard();
    await waitFor(() => expect(screen.getByText(/no projects yet/i)).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /^new thesis$/i }));
    fireEvent.change(screen.getByLabelText(/project name/i), { target: { value: "Brand new" } });
    fireEvent.click(screen.getByRole("button", { name: /^create$/i }));
    await waitFor(() => expect(_push).toHaveBeenCalledWith("/chat/projects/p-new"));
  });

  test("shows the user's credit balance in the hero token card", async () => {
    server.use(
      http.post("*/api/v1/projects/list", () => HttpResponse.json([PROJECT])),
      http.post("*/api/v1/auth/me", () => HttpResponse.json({
        id: "u1", email: "jeen@example.com", username: "Jeendeet",
        credit: 184500, is_super_admin: false, created_at: null,
      })),
    );
    renderDashboard();
    await waitFor(() => expect(screen.getByText("184,500")).toBeTruthy());
    expect(screen.getByText(/hello, jeendeet/i)).toBeTruthy();
  });
});
