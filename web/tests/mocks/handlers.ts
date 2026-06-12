import { http, HttpResponse } from "msw";

export const defaultHandlers = [
  http.get("/api/v1/projects", () => HttpResponse.json([])),
  // HomeDashboard renders useMe() (greeting + credit card); a default stub
  // keeps onUnhandledRequest:"error" from failing tests that don't care
  // about the user payload. Wildcard host because apiFetch (lib/api.js)
  // requests an absolute NEXT_PUBLIC_API_BASE, not a relative /api/v1 path.
  http.get("*/api/v1/auth/me", () => HttpResponse.json({
    id: "u-test", email: "test@example.com", username: null,
    credit: 0, is_super_admin: false, created_at: null,
  })),
];
