import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatInput } from "./ChatInput";


describe("ChatInput", () => {
  test("calls onSubmit with text and clears", async () => {
    const onSubmit = vi.fn();
    render(<ChatInput onSubmit={onSubmit} onFileDrop={() => {}} disabled={false} />);
    const textarea = screen.getByRole("textbox");
    await userEvent.type(textarea, "hello world");
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    expect(onSubmit).toHaveBeenCalledWith("hello world");
  });

  test("Enter submits", async () => {
    const onSubmit = vi.fn();
    render(<ChatInput onSubmit={onSubmit} onFileDrop={() => {}} disabled={false} />);
    const textarea = screen.getByRole("textbox") as HTMLTextAreaElement;
    await userEvent.type(textarea, "hello");
    await userEvent.keyboard("{Enter}");
    expect(onSubmit).toHaveBeenCalledWith("hello");
  });

  test("disabled prevents send", async () => {
    const onSubmit = vi.fn();
    render(<ChatInput onSubmit={onSubmit} onFileDrop={() => {}} disabled={true} />);
    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  });

  test("file drop fires onFileDrop", () => {
    const onFileDrop = vi.fn();
    render(<ChatInput onSubmit={() => {}} onFileDrop={onFileDrop} disabled={false} />);
    const zone = screen.getByTestId("file-drop-zone");
    const file = new File(["x"], "test.pdf", { type: "application/pdf" });
    fireEvent.drop(zone, { dataTransfer: { files: [file] } });
    expect(onFileDrop).toHaveBeenCalledWith([file]);
  });
});
