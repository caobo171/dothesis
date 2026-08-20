import { describe, expect, test } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { LocaleProvider } from "../../lib/i18n/LocaleProvider";
import { StartModeTabs } from "./StartModeTabs";

/** The composer reads locale context, and so does this. */
const renderTabs = (props: Record<string, unknown>) =>
  render(<LocaleProvider initialLocale="en" hasCookie>
    <StartModeTabs mode="guided" onChange={() => {}} {...props} /></LocaleProvider>);

describe("StartModeTabs", () => {
  test("offers both modes and marks the selected one", () => {
    renderTabs({ mode: "guided" });
    expect(screen.getByRole("tab", { name: /guided/i }).getAttribute("aria-selected"))
      .toBe("true");
    expect(screen.getByRole("tab", { name: /auto thesis/i }).getAttribute("aria-selected"))
      .toBe("false");
  });

  test("reports the switch", () => {
    const seen: string[] = [];
    renderTabs({ mode: "guided", onChange: (m: string) => seen.push(m) });
    fireEvent.click(screen.getByRole("tab", { name: /auto thesis/i }));
    expect(seen).toEqual(["auto_thesis"]);
  });

  test("reflects the mode it is given", () => {
    renderTabs({ mode: "auto_thesis" });
    expect(screen.getByRole("tab", { name: /auto thesis/i }).getAttribute("aria-selected"))
      .toBe("true");
  });

  test("is disabled while a run is being started", () => {
    renderTabs({ mode: "guided", busy: true });
    expect((screen.getByRole("tab", { name: /guided/i }) as HTMLButtonElement).disabled)
      .toBe(true);
  });
});
