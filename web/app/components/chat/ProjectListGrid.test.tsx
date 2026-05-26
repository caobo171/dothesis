import { describe, expect, test } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../../../tests/setup";
import { ProjectListGrid } from "./ProjectListGrid";


describe("ProjectListGrid", () => {
  test("renders project cards", async () => {
    server.use(
      http.get("/api/v1/projects", () => HttpResponse.json([
        { id: "p1", name: "Leadership Thesis", field: "Marketing", language: "en",
          citation_style: "apa", status: "draft", current_module: "M2",
          context_store: { m1_topic: { confirmed_at: "x" } },
          created_at: "2026-05-27", updated_at: "2026-05-27" },
      ])),
    );
    render(<ProjectListGrid />);
    await waitFor(() => expect(screen.getByText("Leadership Thesis")).toBeTruthy());
  });

  test("renders empty state when no projects", async () => {
    server.use(
      http.get("/api/v1/projects", () => HttpResponse.json([])),
    );
    render(<ProjectListGrid />);
    await waitFor(() => expect(screen.getByText(/no projects yet/i)).toBeTruthy());
  });
});
