import { describe, expect, test } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../../../tests/setup";
import { streamResponse } from "../../../tests/helpers/sseResponse";
import { ChatPane } from "./ChatPane";
import { stashAnalyzeIntent } from "../../lib/bootstrap-payload";
import { LocaleProvider } from "../../lib/i18n/LocaleProvider";

// ChatPane renders ChatHeader, which reads copy through useT — an unwrapped
// render throws before a single assertion runs.
const renderChat = (projectId: string, threadId: string) =>
  render(
    <LocaleProvider initialLocale="en" hasCookie>
      <ChatPane projectId={projectId} threadId={threadId} />
    </LocaleProvider>,
  );


describe("AutoThesis integration", () => {
  test("click button → modal → confirm → run screen → done", async () => {
    // runStatus tracks state across handler calls; starts at null (no active run)
    let runStatus: "running" | "done" | null = null;
    server.use(
      http.post("*/api/v1/projects/p1", () => HttpResponse.json({
        name: "T", context_store: { m1_topic: { research_title: "Leadership" } },
      })),
      http.post("*/api/v1/threads/t1", () => HttpResponse.json({ name: "Main" })),
      http.post("*/api/v1/threads/t1/messages/list", () => HttpResponse.json([])),
      http.post("*/api/v1/projects/p1/runs/list", () => HttpResponse.json({
        // Return the run object whenever we have an active runStatus
        run: runStatus ? { id: "r1", status: runStatus } : null,
      })),
      http.post("*/api/v1/projects/p1/runs/estimate", () => HttpResponse.json({
        estimated_tokens: 20000, credit_balance: 100000, sufficient_credit: true,
      })),
      http.post("*/api/v1/projects/p1/runs", () => {
        // POST creates the run and sets status to running
        runStatus = "running";
        return HttpResponse.json({ run_id: "r1", status: "running" });
      }),
      http.post("*/api/v1/runs/r1", () => HttpResponse.json({
        id: "r1", status: runStatus ?? "running", mode: "auto",
      })),
      http.post("*/api/v1/runs/r1/events", () => streamResponse([
        'data: {"type":"activity","module":"M1","text":"start"}\n\n',
        'data: {"type":"module_complete","module":"M1"}\n\n',
        'data: {"type":"job_done","exports":{"docx":"s3://b/thesis.docx","pdf":"s3://b/thesis.pdf"}}\n\n',
      ])),
    );

    renderChat("p1", "t1");

    // The trigger lives in the composer's Quick actions menu (moved out of the
    // header to reclaim its space).
    await waitFor(() => screen.getByRole("button", { name: /quick actions/i }));
    fireEvent.click(screen.getByRole("button", { name: /quick actions/i }));

    // Click the trigger → opens the modal, whose confirm button carries the
    // SAME "Auto Thesis" label. Every query below is scoped to the dialog so
    // the two can never be confused for each other.
    await waitFor(() => screen.getByRole("button", { name: /^auto thesis$/i }));
    fireEvent.click(screen.getByRole("button", { name: /^auto thesis$/i }));
    await waitFor(() => screen.getByRole("dialog"));

    // Modal has pre-filled topic + estimate
    await waitFor(() => expect(screen.getByDisplayValue("Leadership")).toBeTruthy());

    // Wait for estimate to load so the confirm button is enabled
    const dialog = screen.getByRole("dialog");
    await waitFor(() => expect(
      within(dialog).getByRole("button", { name: /^auto thesis$/i })).not.toBeDisabled());

    // Confirm
    fireEvent.click(within(dialog).getByRole("button", { name: /^auto thesis$/i }));

    // The run takes over the main pane — no drawer, and no composer, because
    // there is nothing for the student to reply to.
    await waitFor(() => screen.getByText(/writing your thesis/i), { timeout: 5000 });
    expect(screen.queryByPlaceholderText(/reply to dothesis/i)).toBeNull();
    // Module badge turns green after module_complete (design-token class from
    // the 2026-06-10 DoThesis.html restyle).
    await waitFor(() => {
      expect(screen.getByTestId("dot-M1")).toHaveClass("bg-[var(--ok-fg)]");
    }, { timeout: 5000 });

    // After job_done the same screen becomes the payoff.
    await waitFor(() => expect(screen.getByText(/download docx/i)).toBeTruthy(), { timeout: 5000 });
  }, 15000);

  // The /new handoff. Pressing "Write my thesis" there IS the confirmation, so
  // arriving in the workspace must start the run — not re-ask for the topic
  // that was typed on the previous screen next to a token estimate.
  test("Auto Thesis chosen on /new starts the run without a confirm dialog", async () => {
    let runStatus: "running" | null = null;
    let startedWith: string | null = null;
    server.use(
      http.post("*/api/v1/projects/p2", () => HttpResponse.json({
        // No m1_topic: /new skips the mid-journey import in Auto Thesis, so a
        // project seconds old has nothing committed. The topic can only come
        // from the stash.
        name: "Untitled thesis", context_store: {},
      })),
      http.post("*/api/v1/threads/t2", () => HttpResponse.json({ name: "Main" })),
      http.post("*/api/v1/threads/t2/messages/list", () => HttpResponse.json([])),
      http.post("*/api/v1/projects/p2/runs/list", () => HttpResponse.json({
        run: runStatus ? { id: "r2", status: runStatus } : null,
      })),
      http.post("*/api/v1/projects/p2/runs/estimate", () => HttpResponse.json({
        estimated_tokens: 20000, credit_balance: 100000, sufficient_credit: true,
      })),
      http.post("*/api/v1/projects/p2/runs", async ({ request }) => {
        startedWith = ((await request.json()) as { topic: string }).topic;
        runStatus = "running";
        return HttpResponse.json({ run_id: "r2", status: "running" });
      }),
      http.post("*/api/v1/runs/r2", () => HttpResponse.json({
        id: "r2", status: runStatus ?? "running", mode: "auto",
      })),
      http.post("*/api/v1/runs/r2/events", () => streamResponse([
        'data: {"type":"activity","module":"M1","text":"start"}\n\n',
      ])),
    );

    stashAnalyzeIntent("p2", {
      note: "KOL characteristics and buying behaviour on TikTok Shop",
      attachments: [], autoThesis: true,
    });

    renderChat("p2", "t2");

    // The run starts on its own, with the sentence typed on /new as the topic.
    await waitFor(() => expect(startedWith).toBe(
      "KOL characteristics and buying behaviour on TikTok Shop"), { timeout: 5000 });
    // ...and the run screen is what the student lands on.
    await waitFor(() => screen.getByText(/writing your thesis/i), { timeout: 5000 });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  // Dropped a half-finished thesis and typed nothing. The title is on page 1 of
  // that document, so it gets read back rather than demanded — but it is shown
  // once before six chapters are written on a machine's guess.
  test("files with no typed topic: the title is read from them and confirmed once", async () => {
    let runStatus: "running" | null = null;
    let startedWith: string | null = null;
    server.use(
      http.post("*/api/v1/projects/p3", () => HttpResponse.json({
        name: "Untitled thesis", context_store: {},
      })),
      http.post("*/api/v1/threads/t3", () => HttpResponse.json({ name: "Main" })),
      http.post("*/api/v1/threads/t3/messages/list", () => HttpResponse.json([])),
      // The list poll staying empty is the production race: ChatPane
      // already fetched {run:null} on mount, and "Write my thesis" used to
      // close the dialog then hope this refetch would populate the run
      // screen. If it didn't, the student landed on "Start your thesis".
      http.post("*/api/v1/projects/p3/runs/list", () => HttpResponse.json({
        run: null,
      })),
      http.post("*/api/v1/projects/p3/topic-from-uploads", () => HttpResponse.json({
        research_title: "Ảnh hưởng của đặc điểm KOLs đến hành vi mua sắm",
        source: "_Viet Doan Dung Final.docx",
      })),
      http.post("*/api/v1/projects/p3/runs/estimate", () => HttpResponse.json({
        estimated_tokens: 20350, credit_balance: 997220, sufficient_credit: true,
      })),
      http.post("*/api/v1/projects/p3/runs", async ({ request }) => {
        startedWith = ((await request.json()) as { topic: string }).topic;
        runStatus = "running";
        return HttpResponse.json({ run_id: "r3", status: "running" });
      }),
      http.post("*/api/v1/runs/r3", () => HttpResponse.json({
        id: "r3", status: runStatus ?? "running", mode: "auto",
      })),
      http.post("*/api/v1/runs/r3/events", () => streamResponse([
        'data: {"type":"activity","module":"M1","text":"start"}\n\n',
      ])),
    );

    stashAnalyzeIntent("p3", {
      note: "",
      attachments: [{ upload_id: "u1", filename: "_Viet Doan Dung Final.docx",
                      size_bytes: 10, mime_type: "application/pdf" }],
      autoThesis: true,
    });

    renderChat("p3", "t3");

    // The derived title is shown for confirmation — not started behind their back.
    await waitFor(() => screen.getByRole("dialog"), { timeout: 5000 });
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/we read your files/i)).toBeTruthy();
    await waitFor(() => expect(
      within(dialog).getByDisplayValue(/Ảnh hưởng của đặc điểm KOLs/)).toBeTruthy());
    expect(startedWith).toBeNull();   // nothing spent yet

    fireEvent.click(within(dialog).getByRole("button", { name: /write my thesis/i }));
    await waitFor(() => expect(startedWith).toBe(
      "Ảnh hưởng của đặc điểm KOLs đến hành vi mua sắm"), { timeout: 5000 });
    // The run screen must take over even when /runs/list is still empty —
    // the start response is enough to know a run exists.
    await waitFor(() => screen.getByText(/writing your thesis/i), { timeout: 5000 });
    expect(screen.queryByText(/start your thesis/i)).toBeNull();
  }, 15000);

  // The finished run owns the screen only until there is a conversation to
  // show. Otherwise every later visit to a project that once ran Auto Thesis
  // would open on a run report instead of the thread the student was using.
  test("a finished run does not take over a thread that has messages in it", async () => {
    server.use(
      http.post("*/api/v1/projects/p4", () => HttpResponse.json({
        name: "T", context_store: { m1_topic: { research_title: "Leadership" } },
      })),
      http.post("*/api/v1/threads/t4", () => HttpResponse.json({ name: "Main" })),
      http.post("*/api/v1/threads/t4/messages/list", () => HttpResponse.json([
        { id: 1, role: "user", content: "can you shorten chapter 4?",
          created_at: "2026-08-21T00:00:00Z" },
        { id: 2, role: "assistant", content: "Sure — here's a tighter version.",
          created_at: "2026-08-21T00:00:01Z" },
      ])),
      http.post("*/api/v1/projects/p4/runs/list", () => HttpResponse.json({
        run: { id: "r4", status: "done" },
      })),
      http.post("*/api/v1/runs/r4", () => HttpResponse.json({ id: "r4", status: "done" })),
      http.post("*/api/v1/runs/r4/events", () => streamResponse([])),
    );

    renderChat("p4", "t4");

    await waitFor(() => expect(screen.getByText(/shorten chapter 4/i)).toBeTruthy());
    expect(screen.queryByText(/your thesis is ready/i)).toBeNull();
    // The composer is back — this is a conversation again.
    expect(screen.getByPlaceholderText(/reply to dothesis/i)).toBeTruthy();
  });

  test("ask in chat leaves a way back to the run", async () => {
    // "Ask a question about it" used to be a one-way door: it hid the run
    // and the only way back lived inside Quick actions, which nobody looking
    // at an empty thread would open. A live run they just stepped away from
    // has to keep a visible return.
    server.use(
      http.post("*/api/v1/projects/p5", () => HttpResponse.json({
        name: "Untitled thesis",
        context_store: { m1_topic: { research_title: "Leadership" } },
      })),
      http.post("*/api/v1/threads/t5", () => HttpResponse.json({ name: "Main" })),
      http.post("*/api/v1/threads/t5/messages/list", () => HttpResponse.json([])),
      http.post("*/api/v1/projects/p5/runs/list", () => HttpResponse.json({
        run: { id: "r5", status: "running" },
      })),
      http.post("*/api/v1/runs/r5", () => HttpResponse.json({
        id: "r5", status: "running", mode: "auto",
        started_at: new Date().toISOString(),
      })),
      http.post("*/api/v1/runs/r5/events", () => streamResponse([
        'data: {"type":"activity","module":"M1","text":"start"}\n\n',
      ])),
    );

    renderChat("p5", "t5");
    await waitFor(() => screen.getByText(/writing your thesis/i));

    fireEvent.click(screen.getByRole("button", { name: /ask a question about it/i }));
    await waitFor(() => expect(screen.queryByText(/writing your thesis/i)).toBeNull());
    expect(screen.getByPlaceholderText(/reply to dothesis/i)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /back to auto thesis/i }));
    await waitFor(() => screen.getByText(/writing your thesis/i));
  });
});
