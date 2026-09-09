import { describe, expect, test, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import LoginPage from "./page";

const login = vi.fn();
const goToNext = vi.fn();
const apiFetch = vi.fn();

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
}));

vi.mock("../lib/auth-context", () => ({
  useAuth: () => ({ login, acceptTokenPayload: vi.fn() }),
}));

// Mocked rather than driven through MSW: goToNext ends in
// window.location.assign, which jsdom refuses to implement.
vi.mock("../lib/nextPath", () => ({
  goToNext: (raw: string | null) => goToNext(raw),
  safeNextPath: (raw: string | null) => raw ?? "/",
}));

vi.mock("../lib/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

beforeEach(() => {
  vi.clearAllMocks();
  // Answers true to every query, which AuthShell and ProductMock read as: this
  // viewport is wide enough for the side panel (so it mounts at all), and the
  // reader wants reduced motion (so its demo settles on the finished draft with
  // no interval running under the assertions).
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

describe("LoginPage", () => {
  test("renders the form inside the split shell, with the demo beside it", () => {
    render(<LoginPage />);

    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();

    // The explainer panel — the same ProductMock the landing hero renders.
    expect(screen.getByText(/One thread, from a topic idea/)).toBeInTheDocument();
    expect(screen.getByText("Draft ready")).toBeInTheDocument();
  });

  test("signs in and follows the post-login destination", async () => {
    const user = userEvent.setup();
    login.mockResolvedValue(undefined);
    render(<LoginPage />);

    await user.type(screen.getByLabelText("Email"), "student@example.com");
    await user.type(screen.getByLabelText("Password"), "hunter2hunter2");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() =>
      expect(login).toHaveBeenCalledWith("student@example.com", "hunter2hunter2"),
    );
    expect(goToNext).toHaveBeenCalled();
  });

  test("an unverified account offers to resend the verification email", async () => {
    const user = userEvent.setup();
    login.mockRejectedValue({
      body: { detail: { error: { code: "unverified", email: "student@example.com" } } },
    });
    apiFetch.mockResolvedValue({});
    render(<LoginPage />);

    await user.type(screen.getByLabelText("Email"), "student@example.com");
    await user.type(screen.getByLabelText("Password"), "hunter2hunter2");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    const resend = await screen.findByRole("button", { name: "Resend email" });
    await user.click(resend);

    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith("/auth/resend-verification", {
        method: "POST",
        body: { email: "student@example.com" },
      }),
    );
    expect(await screen.findByText("Sent. Check your inbox.")).toBeInTheDocument();
  });

  test("a Google-linked account is pointed at the Google button", async () => {
    const user = userEvent.setup();
    login.mockRejectedValue({
      body: { detail: { error: { code: "use_google" } } },
    });
    render(<LoginPage />);

    await user.type(screen.getByLabelText("Email"), "student@example.com");
    await user.type(screen.getByLabelText("Password"), "hunter2hunter2");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText(/linked to Google/)).toBeInTheDocument();
  });
});
