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
    // The live activity sits UNDER the status word now, not in place of it: the
    // running row was the only one on screen that never said what state it was in.
    await waitFor(() => expect(screen.getByText(/screening 42 sources/i)).toBeTruthy());
    expect(screen.getByText(/running for 12 min/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /stop run/i })).toBeTruthy();
  });

  // A run that cannot continue is not a run in progress. On a measured run M4
  // could not find the student's dataset, refused to invent numbers, and flagged
  // a blocker — then this screen went on showing a spinner and "IN PROGRESS"
  // over a module that was waiting for a human who had not been told.
  test("a blocked module says what it needs, instead of spinning", async () => {
    server.use(
      runRow("blocked1", "running", { phase: "M4" }),
      events("blocked1"),
      http.post("*/api/v1/projects/p1/roadmap", () => HttpResponse.json({
        modules: [], next_action: {},
        tasks: [{
          id: "t1", module: "M4", substep: "run_per_step", status: "open",
          title: "Thiếu dữ liệu khảo sát để chạy phân tích",
          why: "Dự án chưa có tệp dữ liệu thực tế hoặc tệp kết quả SPSS/SmartPLS.",
        }],
      })),
    );
    renderView({ runId: "blocked1" });

    await waitFor(() => expect(
      screen.getByTestId("dot-M4").className).toMatch(/pause-bg/));
    expect(screen.getByText(/Thiếu dữ liệu khảo sát/)).toBeTruthy();
    // And it must not also claim to be busy on the same row.
    expect(screen.queryByTestId("busy-M4")).toBeNull();
  });

  test("a finished run reports how long it took, not how long ago it started", async () => {
    // Seen on a run that took 27 minutes and had been sitting on screen since:
    // "Đã chạy 352 phút". Elapsed was Date.now() − started_at on every status,
    // so a finished run's number kept climbing for as long as the tab was open.
    server.use(
      runRow("elapsed1", "done", {
        started_at: new Date(Date.now() - 300 * 60_000).toISOString(),
        finished_at: new Date(Date.now() - 273 * 60_000).toISOString(),
      }),
      events("elapsed1"),
    );
    renderView({ runId: "elapsed1" });

    await waitFor(() => expect(screen.getByText(/27 min/i)).toBeTruthy());
    expect(screen.queryByText(/300 min/)).toBeNull();
  });

  test("a live run still counts up from its start", async () => {
    server.use(
      runRow("elapsed2", "running", {
        started_at: new Date(Date.now() - 12 * 60_000).toISOString(),
      }),
      events("elapsed2"),
    );
    renderView({ runId: "elapsed2" });

    await waitFor(() => expect(screen.getByText(/12 min/i)).toBeTruthy());
  });

  test("a blocked run gives the student somewhere to answer", async () => {
    // Naming the blocker and leaving it there is half a feature: the run cannot
    // clear this itself, so the screen has to hand over. The thread is where
    // they can attach the missing file or answer the question.
    const onAskInChat = vi.fn();
    server.use(
      runRow("blocked4", "running", { phase: "M4" }),
      events("blocked4"),
      http.post("*/api/v1/projects/p1/roadmap", () => HttpResponse.json({
        modules: [], next_action: {},
        tasks: [{ id: "t1", module: "M4", status: "open",
                  title: "Chưa có dữ liệu khảo sát để chạy kiểm định",
                  why: "Cần tệp dữ liệu hoặc kết quả SPSS/SmartPLS." }],
      })),
    );
    renderView({ runId: "blocked4", onAskInChat });

    const cta = await screen.findByRole("button", { name: /answer this in chat/i });
    fireEvent.click(cta);
    expect(onAskInChat).toHaveBeenCalled();
  });

  test("no blockers, no amber", async () => {
    server.use(
      runRow("blocked2", "running", { phase: "M4" }),
      events("blocked2"),
      http.post("*/api/v1/projects/p1/roadmap", () => HttpResponse.json({
        modules: [], next_action: {}, tasks: [],
      })),
    );
    renderView({ runId: "blocked2" });

    await waitFor(() => expect(screen.getByTestId("dot-M4")).toBeTruthy());
    expect(screen.getByTestId("dot-M4").className).toMatch(/bg-primary-600/);
  });

  test("a blocker on a module the run already finished does not un-finish it", async () => {
    // Advisor directives sit on modules that are done; they are the student's
    // next job, not evidence that the run stalled.
    server.use(
      runRow("blocked3", "running", { phase: "M4" }),
      events("blocked3"),
      http.post("*/api/v1/projects/p1/roadmap", () => HttpResponse.json({
        modules: [], next_action: {},
        tasks: [{ id: "t2", module: "M1", status: "open", feedback_id: "fb1",
                  title: "Advisor: tighten the research questions" }],
      })),
    );
    renderView({ runId: "blocked3", moduleStatus: { M1: "done" } });

    await waitFor(() => expect(screen.getByTestId("dot-M1")).toBeTruthy());
    expect(screen.getByTestId("dot-M1").className).toMatch(/ok-fg/);
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
