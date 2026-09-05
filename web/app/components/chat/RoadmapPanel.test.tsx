import { describe, expect, test, vi, beforeEach, afterEach } from "vitest";
import { act, render, renderHook, screen, fireEvent, waitFor } from "@testing-library/react";

// Mock the shared authed POST helper (F0 Part C: not raw fetch) before importing
// the component, so RoadmapPanel's load() resolves with the fixture roadmap.
const apiFetch = vi.fn();
vi.mock("@/app/lib/api", () => ({ apiFetch: (...a: any[]) => apiFetch(...a) }));

import { RoadmapPanel, StepBar, StepList, useRoadmap } from "./RoadmapPanel";

const FIXTURE = {
  modules: [{ id: "M1", status: "in_progress", current: "derive_questions",
    substeps: [{ id: "frame_topic", label: "Frame the topic", state: "done" },
               { id: "derive_questions", label: "Derive research questions", state: "current" }] }],
  tasks: [],
  next_action: { module: "M1", substep: "derive_questions",
    title: "Derive research questions", why: "This is the next step.",
    cta_options: ["Derive research questions", "Skip to next module"] },
};

describe("RoadmapPanel", () => {
  beforeEach(() => {
    apiFetch.mockReset();
    apiFetch.mockResolvedValue(FIXTURE);
  });

  test("renders the Next card and posts a CTA to chat", async () => {
    const onSend = vi.fn();
    render(<RoadmapPanel data={FIXTURE as any} onSendMessage={onSend} />);
    // getByText was ambiguous here — the Next card's TITLE and its CTA button
    // carry the same string, so it matched two nodes and threw. Ask for the
    // button, which is what this test is actually about.
    await waitFor(() => screen.getByRole("button", { name: /Derive research questions/ }));
    fireEvent.click(screen.getByRole("button", { name: /Derive research questions/ }));
    expect(onSend).toHaveBeenCalledWith("Derive research questions");
  });

  test("without onSendMessage the panel is read-only (no CTA buttons)", async () => {
    render(<RoadmapPanel data={FIXTURE as any} />);
    await waitFor(() => screen.getByTestId("roadmap-panel"));
    expect(screen.queryByRole("button")).toBeNull();
  });

  test("renders the F11 timeline card with an on-track/behind badge", async () => {
    render(<RoadmapPanel data={{
      ...FIXTURE,
      timeline: { this_week: "Data analysis", on_track: false, weeks_behind: 2 },
    } as any} />);
    await waitFor(() => screen.getByTestId("timeline-card"));
    expect(screen.getByText("This week: Data analysis")).toBeTruthy();
    expect(screen.getByText(/2 week\(s\) behind/)).toBeTruthy();
  });

  test("no timeline card when the plan is absent", async () => {
    render(<RoadmapPanel data={FIXTURE as any} />); // no `timeline` key
    await waitFor(() => screen.getByTestId("roadmap-panel"));
    expect(screen.queryByTestId("timeline-card")).toBeNull();
  });
});

describe("module sub-steps on the module card", () => {
  const SUBS = [
    { id: "a", label: "Frame the topic", state: "done" as const },
    { id: "b", label: "Propose titles", state: "done" as const },
    { id: "c", label: "Derive research questions", state: "current" as const },
    { id: "d", label: "Confirm the title", state: "upcoming" as const },
  ];

  test("the panel no longer prints its own per-module checklist", () => {
    // It used to render every module's sub-steps here AND again as cards
    // below — on a finished thesis, 23 struck-through lines of scroll for
    // information already on screen. The Next card stays; the lists moved.
    render(<RoadmapPanel data={FIXTURE as any} />);
    expect(screen.queryByText("Frame the topic")).toBeNull();
  });

  test("StepBar states the progress and keeps the steps on hover", () => {
    const { container } = render(<StepBar substeps={SUBS} />);
    expect(screen.getByText("2/4")).toBeTruthy();
    // The detail is not lost, it just costs no vertical space until wanted.
    const title = container.querySelector("[title]")?.getAttribute("title") ?? "";
    expect(title).toContain("✓ Frame the topic");
    expect(title).toContain("▸ Derive research questions");
  });

  test("StepBar renders nothing when a module has no steps", () => {
    const { container } = render(<StepBar substeps={[]} />);
    expect(container.firstChild).toBeNull();
  });

  test("StepList shows every step in full for the expanded card", () => {
    render(<StepList substeps={SUBS} />);
    for (const s of SUBS) expect(screen.getByText(new RegExp(s.label))).toBeTruthy();
  });
});


// Auto Thesis writes the whole context_store from a subprocess over twenty
// minutes. The roadmap loaded once on mount and then sat there, so the right
// rail told a student to "Confirm M3 is done" while the run was doing M3, and
// never showed the blocker M4 raised after that.
describe("useRoadmap", () => {
  beforeEach(() => {
    apiFetch.mockReset();
    apiFetch.mockResolvedValue(FIXTURE);
  });
  afterEach(() => { vi.useRealTimers(); });

  test("polls while it is given an interval", async () => {
    vi.useFakeTimers();
    renderHook(() => useRoadmap("p1", 0, 15000));
    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));

    await act(async () => { vi.advanceTimersByTime(15_000); });
    expect(apiFetch).toHaveBeenCalledTimes(2);

    await act(async () => { vi.advanceTimersByTime(15_000); });
    expect(apiFetch).toHaveBeenCalledTimes(3);
  });

  test("does not poll when there is nothing to follow", async () => {
    vi.useFakeTimers();
    renderHook(() => useRoadmap("p1"));
    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));

    await act(async () => { vi.advanceTimersByTime(120_000); });
    expect(apiFetch).toHaveBeenCalledTimes(1);
  });

  test("stops polling when it unmounts", async () => {
    vi.useFakeTimers();
    const { unmount } = renderHook(() => useRoadmap("p1", 0, 15000));
    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));

    unmount();
    await act(async () => { vi.advanceTimersByTime(60_000); });
    expect(apiFetch).toHaveBeenCalledTimes(1);
  });
});
