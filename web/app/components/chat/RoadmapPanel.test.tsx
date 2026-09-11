import { describe, expect, test, vi, beforeEach, afterEach } from "vitest";
import { act, render, renderHook, screen, fireEvent, waitFor } from "@testing-library/react";

// Mock the shared authed POST helper (F0 Part C: not raw fetch) before importing
// the component, so RoadmapPanel's load() resolves with the fixture roadmap.
const apiFetch = vi.fn();
vi.mock("@/app/lib/api", () => ({ apiFetch: (...a: any[]) => apiFetch(...a) }));

import { RoadmapPanel, StepBar, StepList, useRoadmap } from "./RoadmapPanel";
import { LocaleProvider } from "@/app/lib/i18n/LocaleProvider";

const FIXTURE = {
  modules: [{ id: "M1", status: "in_progress", current: "derive_questions",
    substeps: [{ id: "frame_topic", label: "Frame the topic", state: "done" },
               { id: "derive_questions", label: "Derive research questions", state: "current" }] }],
  tasks: [],
  next_action: { module: "M1", substep: "derive_questions",
    title: "Derive research questions", why: "This is the next step.",
    cta_options: ["Derive research questions", "Skip to next module"] },
};


// These components read the locale catalogue, and useLocale() throws outside a
// provider. Pinned to "en" (the app default is "vi") so the assertions below
// keep asserting BEHAVIOUR — which step is current, what the panel shows — and
// don't quietly become a test of the Vietnamese copy.
function renderEn(ui: React.ReactElement) {
  return render(<LocaleProvider initialLocale="en">{ui}</LocaleProvider>);
}

describe("RoadmapPanel", () => {
  beforeEach(() => {
    apiFetch.mockReset();
    apiFetch.mockResolvedValue(FIXTURE);
  });

  test("renders the Next card and posts a CTA to chat", async () => {
    const onSend = vi.fn();
    renderEn(<RoadmapPanel data={FIXTURE as any} onSendMessage={onSend} />);
    // getByText was ambiguous here — the Next card's TITLE and its CTA button
    // carry the same string, so it matched two nodes and threw. Ask for the
    // button, which is what this test is actually about.
    await waitFor(() => screen.getByRole("button", { name: /Derive research questions/ }));
    fireEvent.click(screen.getByRole("button", { name: /Derive research questions/ }));
    expect(onSend).toHaveBeenCalledWith("Derive research questions");
  });

  test("without onSendMessage the panel is read-only (no CTA buttons)", async () => {
    renderEn(<RoadmapPanel data={FIXTURE as any} />);
    await waitFor(() => screen.getByTestId("roadmap-panel"));
    expect(screen.queryByRole("button")).toBeNull();
  });

  test("renders the F11 timeline card with an on-track/behind badge", async () => {
    renderEn(<RoadmapPanel data={{
      ...FIXTURE,
      timeline: { this_week: "Data analysis", on_track: false, weeks_behind: 2 },
    } as any} />);
    await waitFor(() => screen.getByTestId("timeline-card"));
    expect(screen.getByText("This week: Data analysis")).toBeTruthy();
    expect(screen.getByText(/2 week\(s\) behind/)).toBeTruthy();
  });

  test("no timeline card when the plan is absent", async () => {
    renderEn(<RoadmapPanel data={FIXTURE as any} />); // no `timeline` key
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
    renderEn(<RoadmapPanel data={FIXTURE as any} />);
    expect(screen.queryByText("Frame the topic")).toBeNull();
  });

  test("StepBar states the progress and keeps the steps on hover", () => {
    const { container } = renderEn(<StepBar substeps={SUBS} />);
    expect(screen.getByText("2/4")).toBeTruthy();
    // The detail is not lost, it just costs no vertical space until wanted.
    const title = container.querySelector("[title]")?.getAttribute("title") ?? "";
    expect(title).toContain("✓ Frame the topic");
    expect(title).toContain("▸ Derive research questions");
  });

  test("StepBar renders nothing when a module has no steps", () => {
    const { container } = renderEn(<StepBar substeps={[]} />);
    expect(container.firstChild).toBeNull();
  });

  test("StepList shows every step in full for the expanded card", () => {
    renderEn(<StepList substeps={SUBS} />);
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

describe("i18n", () => {
  const M3_STEPS = [
    { id: "choose_method", label: "Choose the method", state: "done" as const },
    { id: "design_instrument", label: "Design the instrument", state: "current" as const },
  ];

  test("the questionnaire step is never shown to a student as 'instrument'", () => {
    // The report that started this: "instrument" is correct methodology English
    // and the right STORAGE key, but on a checklist a student reads it as lab
    // equipment. Both locales must name the thing they actually build.
    render(<LocaleProvider initialLocale="vi"><StepList substeps={M3_STEPS} /></LocaleProvider>);
    expect(screen.getByText(/Xây dựng thang đo/)).toBeTruthy();
    expect(screen.queryByText(/instrument/i)).toBeNull();
  });

  test("English says questionnaire, not instrument", () => {
    render(<LocaleProvider initialLocale="en"><StepList substeps={M3_STEPS} /></LocaleProvider>);
    expect(screen.getByText(/Build the questionnaire/)).toBeTruthy();
    expect(screen.queryByText(/instrument/i)).toBeNull();
  });

  test("an unknown step id falls back to the label the API sent", () => {
    // A spine step added to agent/roadmap.py before this catalogue catches up
    // must still read as words, not as a raw message key.
    render(
      <LocaleProvider initialLocale="vi">
        <StepList substeps={[{ id: "brand_new_step", label: "Some new step", state: "current" }]} />
      </LocaleProvider>,
    );
    expect(screen.getByText(/Some new step/)).toBeTruthy();
  });

  test("the Next card is rebuilt in Vietnamese from kind, not echoed from the API", () => {
    const data = {
      modules: [], tasks: [],
      next_action: {
        kind: "confirm_module", module: "M3", substep: "",
        title: "Confirm M3 is done",
        why: "M3 has all its content — confirm it so we move on.",
        cta_options: ["Mark M3 done", "Not yet"],
      },
    };
    render(<LocaleProvider initialLocale="vi"><RoadmapPanel data={data as never} /></LocaleProvider>);
    expect(screen.getByText("Xác nhận hoàn thành M3")).toBeTruthy();
    expect(screen.queryByText(/has all its content/)).toBeNull();
  });

  test("a CTA sends the API's English even when the button reads Vietnamese", () => {
    // The agent's [NEXT] contract is written against those exact phrases, so the
    // wire message must not be translated with the button.
    const sent: string[] = [];
    const data = {
      modules: [], tasks: [],
      next_action: {
        kind: "confirm_module", module: "M3", substep: "",
        title: "Confirm M3 is done", why: "…",
        cta_options: ["Mark M3 done", "Not yet"],
      },
    };
    render(
      <LocaleProvider initialLocale="vi">
        <RoadmapPanel data={data as never} onSendMessage={(m) => sent.push(m)} />
      </LocaleProvider>,
    );
    fireEvent.click(screen.getByText("Đánh dấu M3 đã xong"));
    expect(sent).toEqual(["Mark M3 done"]);
  });
});
