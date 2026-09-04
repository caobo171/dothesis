import { http, HttpResponse } from "msw";

export const defaultHandlers = [
  // POST-only: the projects LIST read moved to POST /projects/list (a
  // create/POST owns the base /projects path).
  http.post("*/api/v1/projects/list", () => HttpResponse.json([])),
  // HomeDashboard renders useMe() (greeting + credit card); a default stub
  // keeps onUnhandledRequest:"error" from failing tests that don't care
  // about the user payload. Wildcard host because apiFetch (lib/api.js)
  // requests an absolute NEXT_PUBLIC_API_BASE, not a relative /api/v1 path.
  http.post("*/api/v1/auth/me", () => HttpResponse.json({
    id: "u-test", email: "test@example.com", username: null,
    credit: 0, is_super_admin: false, created_at: null,
  })),
  // Empty-thread ChatPane fetches this; tests that don't care about
  // suggested actions would otherwise trip onUnhandledRequest:"error".
  http.post("*/api/v1/projects/:id/roadmap", () => HttpResponse.json({})),
];
