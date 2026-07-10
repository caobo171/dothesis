import { describe, expect, test, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// Mock the shared authed POST helper (F0 Part C: not raw fetch) before importing
// the component, so RoadmapPanel's load() resolves with the fixture roadmap.
const apiFetch = vi.fn();
vi.mock("@/app/lib/api", () => ({ apiFetch: (...a: any[]) => apiFetch(...a) }));

import { RoadmapPanel } from "./RoadmapPanel";

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
    render(<RoadmapPanel projectId="abc" onSendMessage={onSend} />);
    await waitFor(() => screen.getByText("Derive research questions"));
    fireEvent.click(screen.getByRole("button", { name: /Derive research questions/ }));
    expect(onSend).toHaveBeenCalledWith("Derive research questions");
  });

  test("without onSendMessage the panel is read-only (no CTA buttons)", async () => {
    render(<RoadmapPanel projectId="abc" />);
    await waitFor(() => screen.getByTestId("roadmap-panel"));
    expect(screen.queryByRole("button")).toBeNull();
  });
});
