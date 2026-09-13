import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { LocaleProvider } from "@/app/lib/i18n/LocaleProvider";
import { ReExportBar } from "../ReExportBar";


// The bar reads its copy from the catalogue now, so it only renders under a
// provider. "en" pinned (the app default is "vi") so these keep asserting
// BEHAVIOUR and don't quietly become a test of the Vietnamese wording.
function renderEn(ui: React.ReactElement) {
  return render(
    <LocaleProvider initialLocale="en" hasCookie>{ui}</LocaleProvider>,
  );
}


describe("ReExportBar", () => {
  it("shows last-export status", () => {
    const t = new Date(Date.now() - 5 * 60 * 1000);
    renderEn(<ReExportBar lastExportAt={t} editsSinceExport={3} onReExport={() => Promise.resolve()} exporting={false} />);
    expect(screen.getByText(/last export/i)).toBeInTheDocument();
    expect(screen.getByText(/3 edits/i)).toBeInTheDocument();
  });

  it("calls onReExport when button clicked", async () => {
    const onReExport = vi.fn().mockResolvedValue(undefined);
    renderEn(<ReExportBar lastExportAt={null} editsSinceExport={0} onReExport={onReExport} exporting={false} />);
    fireEvent.click(screen.getByRole("button", { name: /re-export/i }));
    expect(onReExport).toHaveBeenCalled();
  });

  it("disables the button while exporting", () => {
    renderEn(<ReExportBar lastExportAt={null} editsSinceExport={0} onReExport={() => Promise.resolve()} exporting={true} />);
    expect(screen.getByRole("button", { name: /exporting/i })).toBeDisabled();
  });

  it("shows error state when error provided", () => {
    renderEn(<ReExportBar lastExportAt={null} editsSinceExport={0} onReExport={() => Promise.resolve()} exporting={false} error={new Error("S3 down")} />);
    expect(screen.getByText(/export failed/i)).toBeInTheDocument();
  });
});

describe("leaving the editor", () => {
  it("offers a way back to the chat", () => {
    // The editor replaces the whole workspace — chat, context panel and
    // composer all go. Without this the only way out was the browser's back
    // button or retyping the URL.
    renderEn(
      <ReExportBar lastExportAt={null} editsSinceExport={0}
        onReExport={() => Promise.resolve()} exporting={false} projectId="p1" />,
    );
    const back = screen.getByRole("link", { name: /back to chat/i });
    expect(back).toHaveAttribute("href", "/chat/projects/p1");
  });

  it("omits the link rather than linking nowhere when no project is given", () => {
    renderEn(
      <ReExportBar lastExportAt={null} editsSinceExport={0}
        onReExport={() => Promise.resolve()} exporting={false} />,
    );
    expect(screen.queryByRole("link")).toBeNull();
  });
});
