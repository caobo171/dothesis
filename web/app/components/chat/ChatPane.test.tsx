import { describe, expect, test } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../../../tests/setup";
import { streamResponse } from "../../../tests/helpers/sseResponse";
import { ChatPane } from "./ChatPane";


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

    render(<ChatPane projectId="p1" threadId="t1" />);
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
