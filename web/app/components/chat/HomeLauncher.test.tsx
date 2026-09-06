import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SWRConfig } from "swr";
import { http, HttpResponse } from "msw";
import { server } from "../../../tests/setup";
import { LocaleProvider } from "../../lib/i18n/LocaleProvider";
import { HomeLauncher } from "./HomeLauncher";

// useRouter is read at mount; stub so the launcher renders outside App Router.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

// A FRESH SWR cache per render (provider: new Map) — otherwise "/projects/list"
// cached from an earlier test would mask a later msw override.
const renderLauncher = () =>
  render(
    <SWRConfig value={{ dedupingInterval: 0, provider: () => new Map() }}>
      <LocaleProvider initialLocale="en" hasCookie>
        <HomeLauncher />
      </LocaleProvider>
    </SWRConfig>,
  );

const thesis = (over: Record<string, unknown> = {}) => ({
  id: "p9", name: "Untitled thesis", field: null, language: "en",
  citation_style: "apa", status: "draft", current_module: "M3", focus: "M3",
  module_status: { M1: "done", M2: "done", M3: "in_progress" }, stale_modules: [],
  context_store: { m1_topic: { confirmed_at: "x", research_title: "KOLs and Gen-Z purchase intent" } },
  created_at: "2026-09-01", updated_at: "2026-09-02", ...over,
});


describe("HomeLauncher", () => {
  test("leads with the launcher heading, not the old dashboard hero", () => {
    renderLauncher();
    expect(screen.getByRole("heading", { name: /what can i do for your thesis/i })).toBeTruthy();
  });

  test("a NEW user (no theses) sees sample-prompt cards that prefill the composer", async () => {
    // Default handler returns [] → the new-user prompt cards render.
    renderLauncher();
    fireEvent.click(await screen.findByText(/starting fresh/i));
    const box = screen.getByPlaceholderText(/./) as HTMLTextAreaElement;
    expect(box.value).toMatch(/just starting/i);
  });

  test("Auto Thesis hides the sample-prompt cards (its next step is a run, not a chat)", async () => {
    renderLauncher();
    expect(await screen.findByText(/starting fresh/i)).toBeInTheDocument();
    // StartModeTabs renders each mode as role="tab".
    fireEvent.click(screen.getByRole("tab", { name: /auto thesis/i }));
    expect(screen.queryByText(/starting fresh/i)).not.toBeInTheDocument();
  });

  test("Auto Thesis keeps the theses grid — it is the way back to existing work", async () => {
    // The chips and the grid were hidden together, and they are not the same
    // thing. A chip writes a GUIDED prompt ("I have a draft chapter…") that
    // does not fit the Auto Thesis box, so it goes. The grid is the only route
    // from this screen into a thesis you already have, and watching it vanish
    // on a tab switch reads as "where did my theses go?".
    server.use(
      http.post("*/api/v1/projects/list", () => HttpResponse.json([thesis()])),
    );
    renderLauncher();
    await screen.findByRole("link", { name: /KOLs and Gen-Z purchase intent/i });

    fireEvent.click(screen.getByRole("tab", { name: /auto thesis/i }));

    expect(screen.getByRole("link", { name: /KOLs and Gen-Z purchase intent/i })).toBeTruthy();
  });

  // The grid is a launcher, not an archive: past a certain point it stops being
  // scannable and pushes everything else off the screen. /papers is the page
  // that exists to list them all.
  const many = (n: number) => Array.from({ length: n }, (_, i) => thesis({
    id: `p${i}`,
    context_store: { m1_topic: { confirmed_at: "x", research_title: `Thesis ${i}` } },
  }));

  test("shows at most eight theses", async () => {
    server.use(http.post("*/api/v1/projects/list", () => HttpResponse.json(many(12))));
    renderLauncher();
    await screen.findByRole("link", { name: /Thesis 0/i });

    expect(screen.getByRole("link", { name: /Thesis 7/i })).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Thesis 8/i })).toBeNull();
  });

  test("and sends you to the theses page for the rest", async () => {
    server.use(http.post("*/api/v1/projects/list", () => HttpResponse.json(many(12))));
    renderLauncher();

    const more = await screen.findByRole("link", { name: /all 12/i });
    expect(more.getAttribute("href")).toBe("/papers");
  });

  test("no see-more when they all fit", async () => {
    server.use(http.post("*/api/v1/projects/list", () => HttpResponse.json(many(8))));
    renderLauncher();
    await screen.findByRole("link", { name: /Thesis 7/i });

    expect(screen.queryByRole("link", { name: /all 8/i })).toBeNull();
  });

  test("a RETURNING user sees theses cards: M1 brief, % ring, gray focus line — no M1→M5 bar", async () => {
    server.use(
      http.post("*/api/v1/projects/list", () => HttpResponse.json([thesis()])),
    );
    renderLauncher();
    // The card body is the M1 brief (research_title), NOT the project name.
    const link = await screen.findByRole("link", { name: /KOLs and Gen-Z purchase intent/i });
    expect(link.getAttribute("href")).toBe("/chat/projects/p9");
    expect(screen.queryByText("Untitled thesis")).toBeNull();
    // Progress is the ring only (M1+M2 done, M3 in progress → 50)…
    expect(screen.getByText("50")).toBeInTheDocument();
    // …the M1→M5 module bar was removed (no bare "M1"/"M5" pills).
    expect(screen.queryByText("M1")).toBeNull();
    expect(screen.queryByText("M5")).toBeNull();
    // Gray secondary content: the focus module, spelled out.
    expect(screen.getByText(/M3 · Research Design/i)).toBeInTheDocument();
    // The new-user prompts are replaced by the theses, not shown alongside.
    expect(screen.queryByText(/starting fresh/i)).not.toBeInTheDocument();
  });
});
