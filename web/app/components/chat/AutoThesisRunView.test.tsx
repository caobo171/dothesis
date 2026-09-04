import { describe, expect, test, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../../../tests/setup";
import { streamResponse } from "../../../tests/helpers/sseResponse";
import { AutoThesisRunView } from "./AutoThesisRunView";
import { LocaleProvider } from "../../lib/i18n/LocaleProvider";

const renderView = (props: Partial<Parameters<typeof AutoThesisRunView>[0]> = {}) =>
  render(
    <LocaleProvider initialLocale="en" hasCookie>
      <AutoThesisRunView
        runId="r1"
        projectId="p1"
        topic="KOL characteristics and buying behaviour"
        onAskInChat={() => {}}
        {...props}
      />
    </LocaleProvider>,
  );

// A distinct run id per test. SWR's cache is module-global and its 2s dedupe
// window is longer than these tests take, so sharing an id makes each test
// render the previous one's run row.
const runRow = (id: string, status: string, extra: Record<string, unknown> = {}) =>
  http.post(`*/api/v1/runs/${id}`, () => HttpResponse.json({ id, status, ...extra }));

const events = (id: string, ...lines: string[]) =>
  http.post(`*/api/v1/runs/${id}/events`, () => streamResponse(lines));


describe("AutoThesisRunView", () => {
  test("a live run says nothing is waiting on the student", async () => {
    server.use(
      runRow("live1", "running",
             { started_at: new Date(Date.now() - 12 * 60_000).toISOString() }),
      events("live1", 'data: {"type":"activity","module":"M2","text":"screening 42 sources"}\n\n'),
    );
    renderView({ runId: "live1" });

    await waitFor(() => expect(screen.getByText(/writing your thesis/i)).toBeTruthy());
    // The line this screen exists for: an unattended run that looks like a chat
    // makes students sit and wait for a question that never comes.
    expect(screen.getByText(/nothing here needs an answer from you/i)).toBeTruthy();
    expect(screen.getByText(/KOL characteristics/)).toBeTruthy();
    // The live activity replaces the generic status word on the working module.
    await waitFor(() => expect(screen.getByText(/screening 42 sources/i)).toBeTruthy());
    expect(screen.getByText(/running for 12 min/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /stop run/i })).toBeTruthy();
  });

  test("phase_progress (what the runner actually emits) lights the working module", async () => {
    // Headless writes {type:phase_progress, phase:M2, done:1}, not
    // module_complete. Without this the live checklist stayed all-LOCKED
    // for the whole run, then all-LOCKED again when it finished.
    server.use(
      runRow("prog1", "running"),
      events("prog1",
        'data: {"type":"phase_progress","phase":"M2","done":1,"total":5,"progress":0.2}\n\n',
        'data: {"type":"activity","text":"screening 42 sources"}\n\n',
      ),
    );
    renderView({ runId: "prog1" });

    await waitFor(() => expect(screen.getByTestId("dot-M1")).toHaveClass("bg-[var(--ok-fg)]"));
    expect(screen.getByTestId("dot-M2")).toHaveClass("bg-primary-600");
    expect(screen.getByText(/screening 42 sources/i)).toBeTruthy();
    expect(screen.getByTestId("dot-M5")).toHaveClass("bg-ink-200");
  });

  test("reload of a live run restores progress from the job row, not a blank Starting… list", async () => {
    // On refresh the SSE backlog hasn't arrived yet. The Job row already
    // stores `phase` from the last phase_progress (job_runner writes it),
    // and defaulting a missing fetch to "queued" is how reload painted
    // every module LOCKED under "Starting…".
    server.use(
      runRow("reload1", "running", {
        phase: "M3",
        progress: 0.4,
        started_at: new Date(Date.now() - 8 * 60_000).toISOString(),
      }),
      events("reload1"),
    );
    renderView({ runId: "reload1", initialStatus: "running" });

    await waitFor(() => expect(screen.getByTestId("dot-M1")).toHaveClass("bg-[var(--ok-fg)]"));
    expect(screen.queryByText(/starting/i)).toBeNull();
    expect(screen.getByText(/writing your thesis/i)).toBeTruthy();
    expect(screen.getByTestId("dot-M2")).toHaveClass("bg-[var(--ok-fg)]");
    expect(screen.getByTestId("dot-M3")).toHaveClass("bg-primary-600");
    expect(screen.getByTestId("dot-M5")).toHaveClass("bg-ink-200");
  });

  test("a finished run ticks every module done even without module_complete events", async () => {
    // Production never emits `module_complete`. Headless writes phase_progress
    // and job_done; the Job row is what says the run finished. A checklist
    // still on LOCKED under "Your thesis is ready" is the screen contradicting
    // itself — the student is looking at a finished thesis marked unstarted.
    server.use(
      runRow("doneAll", "done",
             { started_at: new Date(Date.now() - 22 * 60_000).toISOString() }),
      events("doneAll"),
    );
    renderView({ runId: "doneAll" });

    await waitFor(() => expect(screen.getByText(/your thesis is ready/i)).toBeTruthy());
    for (const m of ["M1", "M2", "M3", "M4", "M5"]) {
      expect(screen.getByTestId(`dot-${m}`)).toHaveClass("bg-[var(--ok-fg)]");
      expect(screen.getByTestId(`dot-${m}`)).toHaveTextContent("✓");
    }
    expect(screen.queryByText(/^locked$/i)).toBeNull();
  });

  test("job_done flips the screen to the payoff without waiting for the poll", async () => {
    // The row still reports "running" — the 5s poll hasn't caught up. The
    // stream is the earlier, equally authoritative signal, and a student
    // watching a spinner over a finished thesis is the bug this covers.
    server.use(
      runRow("done1", "running"),
      events("done1",
        'data: {"type":"module_complete","module":"M1"}\n\n',
        'data: {"type":"job_done","exports":{"docx":"s3://b/thesis.docx"}}\n\n',
      ),
    );
    renderView({ runId: "done1" });

    await waitFor(() => expect(screen.getByText(/your thesis is ready/i)).toBeTruthy());
    expect(screen.getByRole("link", { name: /open editor/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /download docx/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /stop run/i })).toBeNull();
  });

  test("a failed run explains that finished work was kept, and offers a resume", async () => {
    const onRetry = vi.fn();
    server.use(
      runRow("fail1", "failed", { error_text: "M4 exceeded its turn budget" }),
      events("fail1", 'data: {"type":"module_complete","module":"M1"}\n\n'),
    );
    renderView({ runId: "fail1", onRetry });

    await waitFor(() => expect(screen.getByText(/stopped before it finished/i)).toBeTruthy());
    expect(screen.getByText(/M4 exceeded its turn budget/)).toBeTruthy();
    // Students assume a stopped run threw everything away and start over,
    // paying twice — so the screen has to say otherwise.
    expect(screen.getByText(/what finished was saved/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /resume run/i }));
    expect(onRetry).toHaveBeenCalled();
  });

  test("the way back to chat is always there", async () => {
    const onAskInChat = vi.fn();
    server.use(runRow("chat1", "running"), events("chat1"));
    renderView({ runId: "chat1", onAskInChat });

    await waitFor(() => expect(screen.getByText(/writing your thesis/i)).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /ask a question about it/i }));
    expect(onAskInChat).toHaveBeenCalled();
  });
});
