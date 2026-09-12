import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ContextPanel, formatExportScope, type UploadItem } from "./ContextPanel";
import { LocaleProvider } from "@/app/lib/i18n/LocaleProvider";

// The two calls a Context row makes: the token mint behind Download, and the
// signed URL AttachmentPreview opens the document with.
const triggerUploadDownload = vi.fn();
const uploadViewUrl = vi.fn();
vi.mock("@/app/lib/api", async (orig) => ({
  ...(await orig() as object),
  triggerUploadDownload: (...a: unknown[]) => triggerUploadDownload(...a),
  uploadViewUrl: (...a: unknown[]) => uploadViewUrl(...a),
}));


const _baseCtx = {
  m1_topic: { research_title: "X", confirmed_at: "2026-05-26" },
  m2_literature: null,
  m3_design: null,
  m4_analysis: null,
  m5_writing: null,
};


// These components read the locale catalogue, and useLocale() throws outside a
// provider. Pinned to "en" (the app default is "vi") so the assertions below
// keep asserting BEHAVIOUR — which step is current, what the panel shows — and
// don't quietly become a test of the Vietnamese copy.
function renderEn(ui: React.ReactElement) {
  return render(<LocaleProvider initialLocale="en">{ui}</LocaleProvider>);
}

describe("export scope labels", () => {
  test("turns chapter protocol scopes into student-facing names", () => {
    expect(formatExportScope("chapter:intro|lit_review|methodology")).toBe("Chương 1–3");
    expect(formatExportScope("chapter:methodology")).toBe("Chương 3");
    expect(formatExportScope("full")).toBe("Toàn bộ luận văn");
  });
});


describe("ContextPanel", () => {
  test("while the project is loading, does not claim modules are empty", () => {
    // Same class of bug as the chat pane flashing "Start your thesis" over a
    // thread that hasn't arrived: the layout used to pass a null store while
    // /projects/{id} was in flight, and every card said "Topic not set yet".
    renderEn(
      <ContextPanel
        loading
        contextStore={{
          m1_topic: null, m2_literature: null, m3_design: null,
          m4_analysis: null, m5_writing: null,
        }}
        uploads={[]}
      />,
    );
    expect(screen.queryByText(/topic not set yet/i)).toBeNull();
    expect(screen.queryByText(/no literature yet/i)).toBeNull();
    expect(screen.queryByText(/no exports yet/i)).toBeNull();
    expect(screen.getByTestId("context-panel")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByTestId("context-panel-skeleton")).toBeTruthy();
    // Chrome stays — this is the panel loading, not the panel missing.
    expect(screen.getByText("Workspace")).toBeTruthy();
  });

  test("renders all 5 module dots", () => {
    renderEn(<ContextPanel contextStore={_baseCtx} uploads={[]} />);
    expect(screen.getByTestId("dot-M1")).toBeTruthy();
    expect(screen.getByTestId("dot-M2")).toBeTruthy();
    expect(screen.getByTestId("dot-M3")).toBeTruthy();
    expect(screen.getByTestId("dot-M4")).toBeTruthy();
    expect(screen.getByTestId("dot-M5")).toBeTruthy();
  });

  test("M1 confirmed → done; M2 locked", () => {
    renderEn(<ContextPanel contextStore={_baseCtx} uploads={[]} />);
    expect(screen.getByTestId("dot-M1")).toHaveClass("bg-[var(--ok-fg)]");
    expect(screen.getByTestId("dot-M2")).toHaveClass("bg-ink-200");
  });

  test("clicking a confirmed module shows its content", () => {
    renderEn(<ContextPanel contextStore={_baseCtx} uploads={[]} />);
    // Open the M1 accordion in the module viewer section
    const viewers = screen.getAllByRole("button");
    // Find the one with "M1 · Topic" prefix
    const m1Viewer = viewers.find(b => /M1.*Topic/i.test(b.textContent ?? ""));
    expect(m1Viewer).toBeTruthy();
    fireEvent.click(m1Viewer!);
    expect(screen.getByText(/research_title/i)).toBeTruthy();
  });

  test("a stale module keeps its done status and gets a note, not a warning badge", () => {
    // This asserted the opposite: an upstream mutate flagged M3 and the panel
    // replaced its progress with an amber "Needs review" badge, while the
    // status itself flipped away from done. Both are gone — the student is
    // told their work may be out of date without it being taken off them.
    renderEn(
      <ContextPanel
        contextStore={{
          m1_topic: { confirmed_at: "2026-06-03" },
          m2_literature: { confirmed_at: "2026-06-03" },
          // M3 was confirmed before the upstream M2 edit landed on it.
          m3_design: { confirmed_at: "2026-06-03" },
          m4_analysis: null,
          m5_writing: null,
        }}
        uploads={[]}
        moduleStatus={{ M1: "done", M2: "done", M3: "done", M4: "locked", M5: "locked" }}
        staleModules={["M3"]}
      />,
    );
    // Still done — staleness does not demote it.
    expect(screen.getByTestId("ctx-M3").getAttribute("data-status")).toBe("done");
    expect(screen.getByText(/may be out of date/i)).toBeTruthy();
    // And nothing tells the student to go review it first.
    expect(screen.queryByText(/needs review/i)).toBeNull();
  });

  test("a legacy needs_review row reads as done and stale", () => {
    // Rows written before the migration can still arrive over the wire mid
    // deploy. needs_review always meant "was done, then invalidated", so it
    // must not render as some unknown fourth state.
    renderEn(
      <ContextPanel
        contextStore={{
          m1_topic: { confirmed_at: "2026-06-03" }, m2_literature: null,
          m3_design: { confirmed_at: "2026-06-03" }, m4_analysis: null, m5_writing: null,
        }}
        uploads={[]}
        moduleStatus={{ M1: "done", M2: "locked", M3: "needs_review", M4: "locked", M5: "locked" }}
      />,
    );
    expect(screen.getByTestId("ctx-M3").getAttribute("data-status")).toBe("done");
    expect(screen.getByText(/may be out of date/i)).toBeTruthy();
  });

  test("missing module_status falls back to legacy context-store derivation", () => {
    // Old projects (no turn yet → module_status is {}) must keep rendering
    // sensibly — no red dots for empty modules, just the legacy locked/done/active.
    renderEn(<ContextPanel contextStore={_baseCtx} uploads={[]} />);
    expect(screen.getByTestId("dot-M1")).toHaveClass("bg-[var(--ok-fg)]");  // confirmed
    expect(screen.getByTestId("dot-M2")).toHaveClass("bg-ink-200");  // locked
  });

  test("uploads list shows filenames", () => {
    renderEn(<ContextPanel contextStore={_baseCtx} uploads={[
      { id: "u1", filename: "paper.pdf", size_bytes: 1234, mime_type: "application/pdf", page_count: 12, uploaded_at: "2026-05-27" },
    ]} />);
    expect(screen.getByText("paper.pdf")).toBeTruthy();
  });

  test("truncated uploads expand on +N more click", () => {
    const uploads = Array.from({ length: 8 }, (_, i) => ({
      id: `u${i}`,
      filename: `file-${i}.docx`,
      size_bytes: 1000,
      mime_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      page_count: null,
      uploaded_at: "2026-05-27",
    }));
    renderEn(<ContextPanel contextStore={_baseCtx} uploads={uploads} />);
    expect(screen.getByText("file-0.docx")).toBeTruthy();
    expect(screen.queryByText("file-7.docx")).toBeNull();
    fireEvent.click(screen.getByText(/\+3 (more|tệp)/i));
    expect(screen.getByText("file-7.docx")).toBeTruthy();
    fireEvent.click(screen.getByText(/show less|thu gọn/i));
    expect(screen.queryByText("file-7.docx")).toBeNull();
  });
});


// --- Context rows: preview + file-type icon -----------------------------

const DOCX: UploadItem = {
  id: "u9",
  filename: "emily_04_1524191809718014.docx",
  size_bytes: 54_000,
  // What the browser actually sends for a .docx shared from a phone: no
  // wordprocessingml, nothing to branch on. The extension is the only signal.
  mime_type: "application/octet-stream",
  page_count: null,
  uploaded_at: "2026-09-10",
};

function _panelWithDocx() {
  return renderEn(<ContextPanel contextStore={_baseCtx} uploads={[DOCX]} />);
}

describe("Context file rows", () => {
  beforeEach(() => {
    triggerUploadDownload.mockReset();
    // Resolves never: DocumentView is allowed to sit on "Đang mở tệp…" instead
    // of dragging docx-preview and a network fetch into jsdom. What's under
    // test is that the modal opened, not what it renders inside.
    uploadViewUrl.mockImplementation(() => new Promise<string>(() => {}));
  });

  test("a .docx carries the Word badge, not the generic FILE sheet", () => {
    _panelWithDocx();
    // The badge letter is drawn as SVG <text>; "W" is Word's, and the bug was
    // this row printing "FILE" for every non-PDF upload.
    expect(screen.getByText("W")).toBeTruthy();
    expect(screen.queryByText("FILE")).toBeNull();
  });

  test("clicking the row previews the file instead of downloading it", () => {
    _panelWithDocx();
    fireEvent.click(screen.getByRole("button", { name: `Preview ${DOCX.filename}` }));
    // Same AttachmentPreview modal the chat chips open — one viewer, one place
    // to fix a rendering bug.
    expect(screen.getByRole("dialog", { name: DOCX.filename })).toBeTruthy();
    expect(triggerUploadDownload).not.toHaveBeenCalled();
  });

  test("the download button still downloads, and does not open the preview", () => {
    triggerUploadDownload.mockResolvedValue(undefined);
    _panelWithDocx();
    fireEvent.click(screen.getByRole("button", { name: `Download ${DOCX.filename}` }));
    expect(triggerUploadDownload).toHaveBeenCalledWith(DOCX.id);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
