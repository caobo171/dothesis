import type { ReactElement } from "react";
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { LocaleProvider } from "@/app/lib/i18n/LocaleProvider";
import { QuickActionsMenu } from "./QuickActionsMenu";


// The menu reads its labels from the catalogue, so it only renders under a
// provider; pin "en" so the assertions below can match English copy.
function renderEn(ui: ReactElement) {
  return render(
    <LocaleProvider initialLocale="en" hasCookie>{ui}</LocaleProvider>,
  );
}


describe("QuickActionsMenu", () => {
  it("keeps the menu closed until the trigger is clicked", () => {
    renderEn(<QuickActionsMenu autoThesisButton={<button>Auto Thesis</button>} />);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /quick actions/i }));
    expect(screen.getByRole("menu")).toBeInTheDocument();
    // The Auto Thesis slot the host passed in is rendered inside the panel.
    expect(screen.getByRole("button", { name: /auto thesis/i })).toBeInTheDocument();
  });

  it("opens upward when placement is 'up' so the composer doesn't clip it", () => {
    renderEn(
      <QuickActionsMenu autoThesisButton={<button>Auto Thesis</button>} placement="up" />,
    );
    fireEvent.click(screen.getByRole("button", { name: /quick actions/i }));
    // bottom-full lifts the panel above the trigger; mt-2 (downward) must not.
    expect(screen.getByRole("menu").className).toContain("bottom-full");
    expect(screen.getByRole("menu").className).not.toContain("top-full");
  });

  it("hides the Export-to-Word action when no onQuickPrompt is wired", () => {
    renderEn(<QuickActionsMenu autoThesisButton={<button>Auto Thesis</button>} />);
    fireEvent.click(screen.getByRole("button", { name: /quick actions/i }));
    expect(screen.queryByText(/export modules/i)).not.toBeInTheDocument();
  });

  it("shows the Export-to-Word action when onQuickPrompt is provided", () => {
    renderEn(
      <QuickActionsMenu
        autoThesisButton={<button>Auto Thesis</button>}
        onQuickPrompt={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /quick actions/i }));
    expect(screen.getByText(/export modules/i)).toBeInTheDocument();
  });
});
