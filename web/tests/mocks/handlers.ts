import { http, HttpResponse } from "msw";

export const defaultHandlers = [
  http.get("/api/v1/projects", () => HttpResponse.json([])),
];
