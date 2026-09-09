import { describe, expect, test, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import SignupPage from "./page";

const push = vi.fn();
const apiFetch = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(""),
}));

vi.mock("../lib/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

// The page never imports this itself, but GoogleSignInButton does, and it
// calls useAuth before the empty-client-id check that would render it away.
vi.mock("../lib/auth-context", () => ({
  useAuth: () => ({ acceptTokenPayload: vi.fn() }),
}));

beforeEach(() => {
  vi.clearAllMocks();
  // True to every query: wide enough for the side panel, and reduced motion —
  // see the fuller note in app/login/page.test.tsx.
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: true,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
      onchange: null,
    })),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SignupPage", () => {
  test("renders the form inside the split shell, with the demo beside it", () => {
    render(<SignupPage />);

    expect(
      screen.getByRole("heading", { name: "Create your account" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Username")).toBeInTheDocument();
    expect(screen.getByText(/One thread, from a topic idea/)).toBeInTheDocument();
  });

  test("signs up and sends the user to wait for verification", async () => {
    const user = userEvent.setup();
    apiFetch.mockResolvedValue({});
    render(<SignupPage />);

    await user.type(screen.getByLabelText("Username"), "minh_anh");
    await user.type(screen.getByLabelText("Email"), "student@example.com");
    await user.type(screen.getByLabelText(/Password/), "hunter2hunter2");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith("/auth/signup", {
        method: "POST",
        body: {
          username: "minh_anh",
          email: "student@example.com",
          password: "hunter2hunter2",
        },
      }),
    );
    expect(push).toHaveBeenCalledWith("/wait-verify?email=student%40example.com");
  });

  // The page's own USERNAME_RE guard is deliberately not tested: the input
  // carries pattern="[a-zA-Z0-9_]{3,32}", so constraint validation refuses the
  // submit and onSubmit never runs. The guard is the fallback behind that, not
  // the path a user takes.
  test("maps a taken email to advice rather than the raw API message", async () => {
    const user = userEvent.setup();
    apiFetch.mockRejectedValue({
      body: { detail: { error: { code: "email_taken" } } },
    });
    render(<SignupPage />);

    await user.type(screen.getByLabelText("Username"), "minh_anh");
    await user.type(screen.getByLabelText("Email"), "student@example.com");
    await user.type(screen.getByLabelText(/Password/), "hunter2hunter2");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(
      await screen.findByText(/already registered. Try signing in instead/),
    ).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
