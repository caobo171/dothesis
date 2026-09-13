import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { LocaleProvider } from "@/app/lib/i18n/LocaleProvider";
import { SaveBar } from "../SaveBar";

function renderEn(props: Partial<Parameters<typeof SaveBar>[0]> = {}) {
  return render(
    <LocaleProvider initialLocale="en" hasCookie>
      <SaveBar
        dirty={false} saving={false} lastSavedAt={null} error={null}
        onSave={() => {}}
        {...props}
      />
    </LocaleProvider>,
  );
}

describe("SaveBar", () => {
  test("offers Save only when there is something to save", () => {
    // A permanently enabled Save teaches nothing about whether the work is
    // stored, which is the whole point of dropping the per-keystroke autosave.
    renderEn();
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();

    renderEn({ dirty: true });
    expect(screen.getByRole("button", { name: "Save" })).toBeTruthy();
  });

  test("says plainly that changes are unsaved", () => {
    renderEn({ dirty: true });
    expect(screen.getByText(/unsaved changes/i)).toBeTruthy();
  });

  test("saving wins over the unsaved marker", () => {
    renderEn({ dirty: true, saving: true });
    expect(screen.getByText(/saving/i)).toBeTruthy();
    expect(screen.queryByText(/unsaved changes/i)).toBeNull();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  test("shows when the last save landed, once clean", () => {
    renderEn({ lastSavedAt: new Date(2026, 0, 1, 14, 5) });
    expect(screen.getByText(/Saved at/)).toBeTruthy();
  });

  test("a failure is announced and still offers the save", () => {
    renderEn({ dirty: true, error: new Error("network") });
    expect(screen.getByRole("alert").textContent).toMatch(/could not save/i);
    expect(screen.getByRole("button", { name: "Save" })).toBeTruthy();
  });

  test("the button calls back", () => {
    const onSave = vi.fn();
    renderEn({ dirty: true, onSave });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onSave).toHaveBeenCalled();
  });
});


describe("seeing what changed", () => {
  test("the unsaved marker opens the diff — knowing THAT something changed is not enough", () => {
    const onShowChanges = vi.fn();
    renderEn({ dirty: true, onShowChanges });
    fireEvent.click(screen.getByRole("button", { name: /unsaved changes/i }));
    expect(onShowChanges).toHaveBeenCalled();
  });

  test("stays inert when the host wires no handler", () => {
    renderEn({ dirty: true });
    expect(screen.getByRole("button", { name: /unsaved changes/i })).toBeDisabled();
  });
});
