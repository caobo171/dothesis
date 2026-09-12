import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LocaleProvider } from "@/app/lib/i18n/LocaleProvider";
import { ChatInput } from "./ChatInput";

function renderEn(ui: React.ReactElement) {
  return render(<LocaleProvider initialLocale="en" hasCookie>{ui}</LocaleProvider>);
}


describe("ChatInput", () => {
  // onSubmit has always carried the attachment list as its second argument;
  // submit is now async as well (it waits for in-flight uploads), so these
  // assert through waitFor on the full call.
  test("calls onSubmit with text and clears", async () => {
    const onSubmit = vi.fn();
    renderEn(<ChatInput onSubmit={onSubmit} onFileDrop={() => {}} disabled={false} />);
    const textarea = screen.getByRole("textbox");
    await userEvent.type(textarea, "hello world");
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith("hello world", [], undefined));
  });

  test("Enter submits", async () => {
    const onSubmit = vi.fn();
    renderEn(<ChatInput onSubmit={onSubmit} onFileDrop={() => {}} disabled={false} />);
    const textarea = screen.getByRole("textbox") as HTMLTextAreaElement;
    await userEvent.type(textarea, "hello");
    await userEvent.keyboard("{Enter}");
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith("hello", [], undefined));
  });

  test("disabled prevents send", async () => {
    const onSubmit = vi.fn();
    renderEn(<ChatInput onSubmit={onSubmit} onFileDrop={() => {}} disabled={true} />);
    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  });

  // The picker's filter greys out anything it omits, so a narrower list than the
  // uploads endpoint's makes a supported format look unsupported. .docx is the
  // one that matters most here — it is what a thesis draft arrives as.
  test("Attach offers every format the uploads endpoint extracts", () => {
    renderEn(<ChatInput onSubmit={() => {}} onFileDrop={() => {}} disabled={false} />);

    const created: HTMLInputElement[] = [];
    const realCreate = document.createElement.bind(document);
    const spy = vi
      .spyOn(document, "createElement")
      .mockImplementation((tag: string, opts?: ElementCreationOptions) => {
        const el = realCreate(tag, opts);
        if (tag === "input") {
          const input = el as HTMLInputElement;
          input.click = vi.fn(); // jsdom has no file dialog
          created.push(input);
        }
        return el;
      });

    fireEvent.click(screen.getByRole("button", { name: /attach/i }));
    spy.mockRestore();

    const picker = created.at(-1);
    expect(picker).toBeDefined();
    expect(picker!.type).toBe("file");
    for (const ext of [".pdf", ".docx", ".txt", ".md", ".markdown"]) {
      expect(picker!.accept).toContain(ext);
    }
  });

  test("paste screenshot attaches image like a file pick", async () => {
    const onFileDrop = vi.fn(async () => ["upload-1"]);
    renderEn(<ChatInput onSubmit={() => {}} onFileDrop={onFileDrop} disabled={false} />);
    const textarea = screen.getByRole("textbox");
    const blob = new File(["img"], "blob", { type: "image/png" });

    fireEvent.paste(textarea, {
      clipboardData: {
        items: [{ type: "image/png", getAsFile: () => blob }],
      },
    });

    await waitFor(() => expect(onFileDrop).toHaveBeenCalled());
    const passed = onFileDrop.mock.calls[0][0] as File[];
    expect(passed).toHaveLength(1);
    expect(passed[0].type).toBe("image/png");
    expect(passed[0].name).toMatch(/^pasted-screenshot-/);
    await screen.findByText(/pasted-screenshot-/);
  });

  test("file drop fires onFileDrop", () => {
    const onFileDrop = vi.fn();
    renderEn(<ChatInput onSubmit={() => {}} onFileDrop={onFileDrop} disabled={false} />);
    const zone = screen.getByTestId("file-drop-zone");
    const file = new File(["x"], "test.pdf", { type: "application/pdf" });
    fireEvent.drop(zone, { dataTransfer: { files: [file] } });
    expect(onFileDrop).toHaveBeenCalledWith([file]);
  });
});

describe("ChatInput attachments", () => {
  const drop = (file: File) => {
    const zone = screen.getByTestId("file-drop-zone");
    fireEvent.drop(zone, { dataTransfer: { files: [file] } });
  };

  test("Send fires immediately even while the upload is still running", async () => {
    // Optimistic: the composer must not sit on a .docx whose extraction takes
    // minutes. The message goes up now; the ids are awaited downstream.
    let resolveUpload: (ids: (string | null)[]) => void = () => {};
    const onFileDrop = vi.fn(
      () => new Promise<(string | null)[]>(res => { resolveUpload = res; }),
    );
    const onSubmit = vi.fn();

    renderEn(<ChatInput onSubmit={onSubmit} onFileDrop={onFileDrop} disabled={false} />);
    drop(new File(["x"], "_Result.docx", { type: "application/octet-stream" }));
    await screen.findByText("_Result.docx");

    await userEvent.type(screen.getByRole("textbox"), "đây là file kết quả");
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    // Sent already — no waiting on the upload.
    expect(onSubmit).toHaveBeenCalledTimes(1);
    const [text, chips, settle] = onSubmit.mock.calls[0];
    expect(text).toBe("đây là file kết quả");
    // The chip rides along so the optimistic bubble can show the file, even
    // though there is no id for it yet.
    expect(chips).toEqual([
      { upload_id: "", filename: "_Result.docx", size_bytes: 1 },
    ]);

    // ...and the caller can await the real id.
    resolveUpload(["upload-1"]);
    await expect(settle()).resolves.toEqual([
      { upload_id: "upload-1", filename: "_Result.docx", size_bytes: 1 },
    ]);
  });

  test("the settle promise rejects when an upload failed, so the send can be undone", async () => {
    const onFileDrop = vi.fn(async () => [null]);   // no id back = failure
    const onSubmit = vi.fn();

    renderEn(<ChatInput onSubmit={onSubmit} onFileDrop={onFileDrop} disabled={false} />);
    drop(new File(["x"], "broken.docx", { type: "application/octet-stream" }));
    await screen.findByText(/Upload failed/i);

    await userEvent.type(screen.getByRole("textbox"), "gửi shop nhé");
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    const settle = onSubmit.mock.calls[0][2];
    // All-or-nothing: never resolve to a partial list, which is how a message
    // ended up claiming a file it never carried.
    await expect(settle()).rejects.toThrow("upload_failed");
  });

  test("a message with no attachment gets no settle callback", async () => {
    const onSubmit = vi.fn();
    renderEn(<ChatInput onSubmit={onSubmit} onFileDrop={() => {}} disabled={false} />);
    await userEvent.type(screen.getByRole("textbox"), "chào shop");
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    expect(onSubmit).toHaveBeenCalledWith("chào shop", [], undefined);
  });
});
