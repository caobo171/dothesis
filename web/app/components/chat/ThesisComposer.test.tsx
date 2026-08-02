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
