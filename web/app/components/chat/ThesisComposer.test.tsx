import { describe, expect, test, vi as viMock } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";

import { LocaleProvider } from "../../lib/i18n/LocaleProvider";
import type { Locale } from "../../lib/i18n/locale";
import { ThesisComposer } from "./ThesisComposer";

/** Renders the composer with real locale context and controlled text state. */
function Harness({
  locale = "en",
  onSubmit = () => {},
  files = [] as File[],
  onAddFiles = () => {},
}: {
  locale?: Locale;
  onSubmit?: () => void;
  files?: File[];
  onAddFiles?: (f: File[] | FileList | null) => void;
}) {
  function Inner() {
    const [value, setValue] = useState("");
    return (
      <ThesisComposer
        value={value}
        onChange={setValue}
        files={files}
        onAddFiles={onAddFiles}
        onRemoveFile={() => {}}
        onSubmit={onSubmit}
        canSubmit={value.trim().length > 0 || files.length > 0}
      />
    );
  }
  return (
    <LocaleProvider initialLocale={locale} hasCookie>
      <Inner />
    </LocaleProvider>
  );
}

describe("ThesisComposer", () => {
  test("a starter chip prefills EDITABLE text rather than submitting", () => {
    // The chip is a starting point the student rewrites — if it submitted, the
    // analysis would run on words they never chose.
    const onSubmit = viMock.fn();
    render(<Harness onSubmit={onSubmit} />);

    fireEvent.click(screen.getByRole("button", { name: "I have data" }));

    const box = screen.getByRole("textbox") as HTMLTextAreaElement;
    expect(box.value).toMatch(/SmartPLS/);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  test("Analyze is disabled until there is text or a file", () => {
    render(<Harness />);
    const analyze = screen.getByRole("button", { name: /Analyze/ });
    expect(analyze).toBeDisabled();

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "I have a topic" } });
    expect(screen.getByRole("button", { name: /Analyze/ })).not.toBeDisabled();
  });

  test("files alone are enough to submit — typing is not required", () => {
    // The whole point of keeping attach: a student who only has a PDF must not
    // be forced to write a sentence first.
    render(<Harness files={[new File(["x"], "draft.pdf")]} />);
    expect(screen.getByRole("button", { name: /Analyze/ })).not.toBeDisabled();
    expect(screen.getByText("draft.pdf")).toBeTruthy();
  });

  test("Enter submits, Shift+Enter does not", () => {
    const onSubmit = viMock.fn();
    render(<Harness onSubmit={onSubmit} />);
    const box = screen.getByRole("textbox");
    fireEvent.change(box, { target: { value: "hello" } });

    fireEvent.keyDown(box, { key: "Enter", shiftKey: true });
    expect(onSubmit).not.toHaveBeenCalled();

    fireEvent.keyDown(box, { key: "Enter" });
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  test("renders Vietnamese when the locale is vi", () => {
    render(<Harness locale="vi" />);
    expect(screen.getByRole("button", { name: /Phân tích/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Mình có dữ liệu" })).toBeTruthy();
    expect(
      (screen.getByRole("textbox") as HTMLTextAreaElement).placeholder,
    ).toMatch(/Cho mình biết bạn đang có gì/);
  });

  test("dropping files calls onAddFiles", () => {
    const onAddFiles = viMock.fn();
    render(<Harness onAddFiles={onAddFiles} />);
    const box = screen.getByRole("textbox").parentElement!;
    fireEvent.drop(box, { dataTransfer: { files: [new File(["x"], "a.pdf")] } });
    expect(onAddFiles).toHaveBeenCalled();
  });

  test("the file input hands over a SNAPSHOT, not the live FileList", () => {
    // The regression this pins: onChange used to pass e.target.files straight
    // through and THEN set e.target.value = "". Clearing the input empties that
    // FileList in place, so a consumer reading it later (a deferred setState
    // updater) got nothing. It presented as "you can only ever attach one
    // file" — React eagerly evaluates the first update from initial state and
    // defers the rest. Reported from the field as "chỉ up dc 1 file".
    const received: unknown[] = [];
    render(<Harness onAddFiles={(f) => received.push(f)} />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const a = new File(["a"], "a.pdf");
    Object.defineProperty(input, "files", { value: [a], configurable: true });
    fireEvent.change(input);

    // An Array survives the input reset; a FileList would not.
    expect(Array.isArray(received[0])).toBe(true);
    expect((received[0] as File[])[0].name).toBe("a.pdf");
    // And the input is cleared, so re-picking the SAME filename still fires.
    expect(input.value).toBe("");
  });
});


// --- Auto Thesis tab --------------------------------------------------------
// The most expensive thing DoThesis does was reachable only through a dropdown
// three screens in. Putting the choice on the start screen is the point of this
// control, so these tests assert it is visible and that it reports the switch.

describe("mode tabs", () => {
  const base = {
    value: "", onChange: () => {}, files: [], onAddFiles: () => {},
    onRemoveFile: () => {}, onSubmit: () => {}, canSubmit: false,
  };
  /** The composer reads locale context, so every render needs the provider —
   *  same reason the Harness above exists. */
  const renderComposer = (props: Record<string, unknown>) =>
    render(<LocaleProvider initialLocale="en" hasCookie><ThesisComposer {...base} {...props} /></LocaleProvider>);

  test("offers both modes, guided selected by default", () => {
    renderComposer({ mode: "guided", onModeChange: () => {} });
    expect(screen.getByRole("tab", { name: /guided/i }).getAttribute("aria-selected"))
      .toBe("true");
    expect(screen.getByRole("tab", { name: /auto thesis/i }).getAttribute("aria-selected"))
      .toBe("false");
  });

  test("clicking Auto Thesis reports the change", () => {
    const seen: string[] = [];
    renderComposer({ mode: "guided", onModeChange: (m: string) => seen.push(m) });
    fireEvent.click(screen.getByRole("tab", { name: /auto thesis/i }));
    expect(seen).toEqual(["auto_thesis"]);
  });

  test("reflects the selected mode it is given", () => {
    renderComposer({ mode: "auto_thesis", onModeChange: () => {} });
    expect(screen.getByRole("tab", { name: /auto thesis/i }).getAttribute("aria-selected"))
      .toBe("true");
  });

  test("starter chips are hidden in Auto Thesis mode", () => {
    // The chips describe situations for a guided conversation ("I have data",
    // "Starting fresh"). In Auto Thesis the next thing that happens is a paid
    // run, so offering conversation openers would misdescribe the button.
    renderComposer({ mode: "auto_thesis", onModeChange: () => {} });
    expect(screen.queryByText(/starting fresh|bắt đầu từ đầu/i)).toBeNull();
  });
});


// --- Auto Thesis speaks in its own voice -----------------------------------
// The tab shipped with the guided copy still around it: heading "Analyze your
// thesis", a placeholder asking what you already have, and an "Analyze" button.
// In Auto Thesis the student is not analysing anything — they are commissioning
// a whole thesis — so the screen has to change voice with the tab, or the tab
// reads as a switch bolted onto someone else's screen.

describe("Auto Thesis copy", () => {
  const base = {
    value: "", onChange: () => {}, files: [], onAddFiles: () => {},
    onRemoveFile: () => {}, onSubmit: () => {}, canSubmit: true,
  };
  const renderIn = (locale: Locale, props: Record<string, unknown>) =>
    render(<LocaleProvider initialLocale={locale} hasCookie>
      <ThesisComposer {...base} {...props} /></LocaleProvider>);

  test("asks for a topic, not for what you already have", () => {
    renderIn("en", { mode: "auto_thesis", onModeChange: () => {} });
    const box = screen.getByRole("textbox") as HTMLTextAreaElement;
    expect(box.placeholder).toMatch(/topic/i);
    expect(box.placeholder).not.toMatch(/what you have/i);
  });

  test("the button commissions a thesis instead of analysing one", () => {
    renderIn("en", { mode: "auto_thesis", onModeChange: () => {} });
    expect(screen.getByRole("button", { name: /write my thesis/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^analyze$/i })).toBeNull();
  });

  test("guided mode keeps its original copy", () => {
    renderIn("en", { mode: "guided", onModeChange: () => {} });
    expect(screen.getByRole("button", { name: /^analyze$/i })).toBeTruthy();
  });

  test("the Auto Thesis copy is translated, not English-only", () => {
    // Vietnamese is the primary market; an English-only mode would read as
    // half-finished exactly where the student is deciding to spend credits.
    renderIn("vi", { mode: "auto_thesis", onModeChange: () => {} });
    const box = screen.getByRole("textbox") as HTMLTextAreaElement;
    expect(box.placeholder).not.toMatch(/topic/i);
    expect(screen.queryByRole("button", { name: /write my thesis/i })).toBeNull();
  });
});
