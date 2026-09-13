import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { LocaleProvider } from "@/app/lib/i18n/LocaleProvider";
import { AutosaveStatus } from "../AutosaveStatus";

function renderEn(props: Partial<Parameters<typeof AutosaveStatus>[0]> = {}) {
  return render(
    <LocaleProvider initialLocale="en" hasCookie>
      <AutosaveStatus
        saving={false} lastSavedAt={null} error={null} onRetry={() => {}}
        {...props}
      />
    </LocaleProvider>,
  );
}

describe("AutosaveStatus", () => {
  test("says the chapter saves itself, since there is no Save button", () => {
    renderEn();
    expect(screen.getByText(/saves automatically/i)).toBeTruthy();
  });

  test("shows when the last save landed", () => {
    renderEn({ lastSavedAt: new Date(2026, 0, 1, 14, 5) });
    expect(screen.getByText(/Saved at/)).toBeTruthy();
  });

  test("a failed save is loud, not a timestamp", () => {
    // The hook gives up after three attempts and set an `error` no component
    // read — a student typing through a dead session saw an ordinary editor.
    renderEn({ error: new Error("network"), lastSavedAt: new Date() });
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toMatch(/could not be saved/i);
    expect(screen.queryByText(/Saved at/)).toBeNull();
  });

  test("and offers the retry that actually re-sends the prose", () => {
    const onRetry = vi.fn();
    renderEn({ error: new Error("network"), onRetry });
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalled();
  });
});
