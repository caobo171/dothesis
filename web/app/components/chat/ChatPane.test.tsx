import { describe, expect, test } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { SWRConfig } from "swr";
import { server } from "../../../tests/setup";
import { streamResponse } from "../../../tests/helpers/sseResponse";
import { ChatPane, _isAutoWritten } from "./ChatPane";


// Wrap component with a fresh SWR cache to prevent cross-test cache bleed.
// Each isolated render gets its own Map() so prior test data never leaks in.
function renderFresh(ui: JSX.Element) {
  return render(
    <SWRConfig value={{ dedupingInterval: 0, provider: () => new Map() }}>
      {ui}
    </SWRConfig>
  );
}


function setupMocks() {
  server.use(
    http.post("*/api/v1/projects/p1", () => HttpResponse.json({
      name: "Test Project",
      context_store: { m1_topic: null },
    })),
    http.post("*/api/v1/threads/t1", () => HttpResponse.json({ name: "Main" })),
    http.post("*/api/v1/projects/p1/runs/list", () => HttpResponse.json({ run: null })),
    http.post("*/api/v1/threads/t1/messages/list", () => HttpResponse.json([])),
  );
}


describe("ChatPane integration", () => {
  test("send → stream → message persisted", async () => {
    setupMocks();
    let postCount = 0;
    // After the POST completes, subsequent GET /messages returns the persisted assistant reply
    let messagesAfterPost = false;
    server.use(
      http.post("/api/v1/threads/t1/messages", () => {
        postCount++;
        messagesAfterPost = true;
        return streamResponse([
          'data: {"type":"token","text":"Hello! "}\n\n',
          'data: {"type":"token","text":"How can I help?"}\n\n',
          'data: {"type":"done"}\n\n',
        ]);
      }),
      http.post("*/api/v1/threads/t1/messages/list", () => {
        // Return persisted messages after the stream so text survives inflight=false
        if (messagesAfterPost) {
          return HttpResponse.json([
            { id: 1, role: "user", content: "hi there", created_at: new Date().toISOString() },
            { id: 2, role: "assistant", content: "Hello! How can I help?", created_at: new Date().toISOString() },
          ]);
        }
        return HttpResponse.json([]);
      }),
    );

    renderFresh(<ChatPane projectId="p1" threadId="t1" />);
    await waitFor(() => screen.getByText("Test Project"));

    const textarea = screen.getByRole("textbox");
    await userEvent.type(textarea, "hi there");
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    // Optimistic user message
    await waitFor(() => expect(screen.getByText("hi there")).toBeTruthy());
    // Streaming reply concatenates (shown during inflight); after done, persisted via SWR revalidation
    await waitFor(() => expect(screen.getByText(/Hello!.*How can I help/)).toBeTruthy());
    expect(postCount).toBe(1);
  });
});

describe("ChatPane widget click integration", () => {
  test("clicking a card synthesizes message and POSTs it", async () => {
    let capturedBody: { text?: string } | null = null;
    server.use(
      http.post("*/api/v1/projects/p1", () => HttpResponse.json({
        name: "Test Project",
        context_store: { m1_topic: null },
      })),
      http.post("*/api/v1/threads/t1", () => HttpResponse.json({ name: "Main" })),
      http.post("*/api/v1/projects/p1/runs/list", () => HttpResponse.json({ run: null })),
      http.post("*/api/v1/threads/t1/messages/list", () => HttpResponse.json([
        {
          id: 1,
          role: "assistant",
          content: "Which field is your research in?",
          created_at: "2026-05-27T00:00:00Z",
          tool_calls_json: {
            widget_type: "card_grid",
            field_name: "field",
            title: "Pick a field",
            options: [
              { value: "Marketing", label: "Marketing", description: "" },
              { value: "Economics", label: "Economics", description: "" },
            ],
            columns: 3,
          },
        },
      ])),
      http.post("/api/v1/threads/t1/messages", async ({ request }) => {
        capturedBody = await request.json() as { text?: string };
        return streamResponse([
          'data: {"type":"token","text":"Got it."}\n\n',
          'data: {"type":"done"}\n\n',
        ]);
      }),
    );

    renderFresh(<ChatPane projectId="p1" threadId="t1" />);

    // The widget renders from the existing message
    await waitFor(() => expect(screen.getByTestId("card-Marketing")).toBeTruthy());

    fireEvent.click(screen.getByTestId("card-Marketing"));

    // The frontend should POST with the synthesized message
    await waitFor(() => expect(capturedBody?.text).toBe("I'd like to study Marketing."));
  });
});

describe("ChatPane list_editor integration", () => {
  test("clicking Confirm on a themes list_editor synthesizes message and POSTs it", async () => {
    let capturedBody: { text?: string } | null = null;
    server.use(
      http.post("*/api/v1/projects/p1", () => HttpResponse.json({
        name: "Test Project",
        context_store: { m1_topic: null },
      })),
      http.post("*/api/v1/threads/t1", () => HttpResponse.json({ name: "Main" })),
      http.post("*/api/v1/projects/p1/runs/list", () => HttpResponse.json({ run: null })),
      http.post("*/api/v1/threads/t1/messages/list", () => HttpResponse.json([
        {
          id: 1,
          role: "assistant",
          content: "Confirm your themes",
          created_at: "2026-05-27T00:00:00Z",
          tool_calls_json: {
            widget_type: "list_editor",
            field_name: "themes",
            title: "Themes",
            initial_items: [
              { id: "t1", text: "Cách thức lãnh đạo",
                sub_items: [{ id: "s1", text: "Tầm nhìn" }] },
              { id: "t2", text: "Biểu hiện gắn kết", sub_items: [] },
            ],
            allow_nested: true,
            confirm_label: "Confirm", reset_label: "Reset to suggested",
          },
        },
      ])),
      http.post("/api/v1/threads/t1/messages", async ({ request }) => {
        capturedBody = await request.json() as { text?: string };
        return streamResponse([
          'data: {"type":"token","text":"Got it."}\n\n',
          'data: {"type":"done"}\n\n',
        ]);
      }),
    );

    renderFresh(<ChatPane projectId="p1" threadId="t1" />);

    await waitFor(() => expect(screen.getByTestId("list-editor-themes")).toBeTruthy());

    fireEvent.click(screen.getByTestId("list-editor-confirm"));

    await waitFor(() => expect(capturedBody?.text).toContain("My themes are:"));
    expect(capturedBody?.text).toContain("Cách thức lãnh đạo");
    expect(capturedBody?.text).toContain("(Sub: Tầm nhìn)");
  });

  test("clicking Confirm on an analysis_outline list_editor synthesizes POST body", async () => {
    let capturedBody: { text?: string } | null = null;
    server.use(
      http.post("*/api/v1/projects/p1", () => HttpResponse.json({
        name: "Test Project",
        context_store: { m1_topic: null },
      })),
      http.post("*/api/v1/threads/t1", () => HttpResponse.json({ name: "Main" })),
      http.post("*/api/v1/projects/p1/runs/list", () => HttpResponse.json({ run: null })),
      http.post("*/api/v1/threads/t1/messages/list", () => HttpResponse.json([
        {
          id: 1,
          role: "assistant",
          content: "Confirm the outline below",
          created_at: "2026-05-27T00:00:00Z",
          tool_calls_json: {
            widget_type: "list_editor",
            field_name: "analysis_outline",
            title: "SPSS outline",
            initial_items: [
              { id: "s0", text: "Descriptive Statistics", sub_items: [], meta: {} },
              { id: "s1", text: "Reliability (Cronbach's Alpha)", sub_items: [],
                meta: { thresholds: "α ≥ 0.7" } },
            ],
            allow_nested: false,
            confirm_label: "Confirm", reset_label: "Reset to suggested",
          },
        },
      ])),
      http.post("/api/v1/threads/t1/messages", async ({ request }) => {
        capturedBody = await request.json() as { text?: string };
        return streamResponse([
          'data: {"type":"token","text":"Running..."}\n\n',
          'data: {"type":"done"}\n\n',
        ]);
      }),
    );

    renderFresh(<ChatPane projectId="p1" threadId="t1" />);

    await waitFor(() => expect(screen.getByTestId("list-editor-analysis_outline")).toBeTruthy());

    fireEvent.click(screen.getByTestId("list-editor-confirm"));

    await waitFor(() => expect(capturedBody?.text).toContain("My analysis outline:"));
    expect(capturedBody?.text).toContain("1. Descriptive Statistics");
    expect(capturedBody?.text).toContain("2. Reliability (Cronbach's Alpha) — α ≥ 0.7");
  });
});

describe("ChatPane → ChatHeader integration (SP6.5)", () => {
  it("passes hasChapters=true when m5_writing.chapters has entries", async () => {
    // Mock the project fetch to return a non-empty chapters map, which should
    // cause ChatHeader to render the "Open editor" link for the project.
    server.use(
      http.post("*/api/v1/projects/p1", () =>
        HttpResponse.json({
          name: "Test Project",
          context_store: {
            m1_topic: null,
            m5_writing: {
              chapters: {
                introduction: { title: "Introduction", content: "..." },
              },
            },
          },
        }),
      ),
      http.post("*/api/v1/threads/t1", () => HttpResponse.json({ name: "Main" })),
      http.post("*/api/v1/projects/p1/runs/list", () => HttpResponse.json({ run: null })),
      http.post("*/api/v1/threads/t1/messages/list", () => HttpResponse.json([])),
    );

    renderFresh(<ChatPane projectId="p1" threadId="t1" />);

    // The "Open editor" link is rendered by ChatHeader only when hasChapters &&
    // projectId are both truthy — wait for it to appear.
    await waitFor(() => expect(screen.getByRole("link", { name: /open editor/i })).toBeTruthy());

    const link = screen.getByRole("link", { name: /open editor/i });
    expect(link).toHaveAttribute("href", "/chat/projects/p1/editor");
  });

  it("hides Open editor when chapters is empty", async () => {
    // An empty chapters map means hasChapters=false — the link must NOT render.
    server.use(
      http.post("*/api/v1/projects/p1", () =>
        HttpResponse.json({
          name: "Test Project",
          context_store: {
            m1_topic: null,
            m5_writing: { chapters: {} },
          },
        }),
      ),
      http.post("*/api/v1/threads/t1", () => HttpResponse.json({ name: "Main" })),
      http.post("*/api/v1/projects/p1/runs/list", () => HttpResponse.json({ run: null })),
      http.post("*/api/v1/threads/t1/messages/list", () => HttpResponse.json([])),
    );

    renderFresh(<ChatPane projectId="p1" threadId="t1" />);

    // Wait for project name to confirm data has loaded, then assert link absent.
    await waitFor(() => screen.getByText("Test Project"));
    expect(screen.queryByRole("link", { name: /open editor/i })).toBeNull();
  });
});

// --- "auto-written" must mean auto-written ------------------------------
describe("auto-written empty state", () => {
  const base = {
    name: "T",
    module_status: { M1: "done", M2: "done", M3: "done", M4: "done", M5: "done" },
    context_store: {},
  };

  test("an IMPORTED chapter does not count as us writing the thesis", () => {
    // The import carves the student's own final chapter into final_sections.
    // That used to flip the same flag the editor link uses, so a project with
    // M5 in_progress, no generated chapters and no export was greeted with
    // "This thesis was auto-written — all modules are complete". Telling
    // someone their unfinished thesis is done is the worst thing this screen
    // can do: they stop working on it.
    const project = {
      ...base,
      module_status: { ...base.module_status, M5: "in_progress" },
      context_store: {
        m5_writing: {
          chapters: {},
          final_sections: [{ chapter_name: "conclusion", prose: "x".repeat(500) }],
          export_artifacts: [],
        },
      },
    };
    expect(_isAutoWritten(project)).toBe(false);
  });

  test("generated chapters with every module done DO count", () => {
    expect(_isAutoWritten({
      ...base,
      context_store: { m5_writing: { chapters: { intro: { prose: "i" } } } },
    })).toBe(true);
  });

  test("a docx export with every module done counts too", () => {
    expect(_isAutoWritten({
      ...base,
      context_store: {
        m5_writing: { chapters: {}, export_artifacts: [{ kind: "docx", download_url: "/x" }] },
      },
    })).toBe(true);
  });

  test("chapters but a module still open is not 'all modules are complete'", () => {
    expect(_isAutoWritten({
      ...base,
      module_status: { ...base.module_status, M2: "needs_review" },
      context_store: { m5_writing: { chapters: { intro: { prose: "i" } } } },
    })).toBe(false);
  });
});
