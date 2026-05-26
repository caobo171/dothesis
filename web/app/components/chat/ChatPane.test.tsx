import { describe, expect, test } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { SWRConfig } from "swr";
import { server } from "../../../tests/setup";
import { streamResponse } from "../../../tests/helpers/sseResponse";
import { ChatPane } from "./ChatPane";


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
    http.get("/api/v1/projects/p1", () => HttpResponse.json({
      name: "Test Project",
      context_store: { m1_topic: null },
    })),
    http.get("/api/v1/threads/t1", () => HttpResponse.json({ name: "Main" })),
    http.get("/api/v1/projects/p1/runs", () => HttpResponse.json({ run: null })),
    http.get("/api/v1/threads/t1/messages", () => HttpResponse.json([])),
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
      http.get("/api/v1/threads/t1/messages", () => {
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
      http.get("/api/v1/projects/p1", () => HttpResponse.json({
        name: "Test Project",
        context_store: { m1_topic: null },
      })),
      http.get("/api/v1/threads/t1", () => HttpResponse.json({ name: "Main" })),
      http.get("/api/v1/projects/p1/runs", () => HttpResponse.json({ run: null })),
      http.get("/api/v1/threads/t1/messages", () => HttpResponse.json([
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
      http.get("/api/v1/projects/p1", () => HttpResponse.json({
        name: "Test Project",
        context_store: { m1_topic: null },
      })),
      http.get("/api/v1/threads/t1", () => HttpResponse.json({ name: "Main" })),
      http.get("/api/v1/projects/p1/runs", () => HttpResponse.json({ run: null })),
      http.get("/api/v1/threads/t1/messages", () => HttpResponse.json([
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
});
