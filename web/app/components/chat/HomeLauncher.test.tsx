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
