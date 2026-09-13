import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ContextPanel, ExportRowItem, formatExportScope, type UploadItem } from "./ContextPanel";
import { LocaleProvider } from "@/app/lib/i18n/LocaleProvider";
import { en as enMessages } from "@/app/lib/i18n/messages/en";
import { vi as viMessages } from "@/app/lib/i18n/messages/vi";

// The two calls a Context row makes: the token mint behind Download, and the
// signed URL AttachmentPreview opens the document with.
const triggerUploadDownload = vi.fn();
const uploadViewUrl = vi.fn();
// The same pair for an EXPORT row: the token mint behind its Download, and the
// same-origin /raw URL its preview renders from.
const triggerExportDownload = vi.fn();
const exportViewUrl = vi.fn();
vi.mock("@/app/lib/api", async (orig) => ({
  ...(await orig() as object),
  triggerUploadDownload: (...a: unknown[]) => triggerUploadDownload(...a),
  uploadViewUrl: (...a: unknown[]) => uploadViewUrl(...a),
  triggerExportDownload: (...a: unknown[]) => triggerExportDownload(...a),
  exportViewUrl: (...a: unknown[]) => exportViewUrl(...a),
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
  // hasCookie, or the provider treats initialLocale as a guess and re-negotiates
  // back to the "vi" default — the English assertions would be asserting nothing.
  return render(<LocaleProvider initialLocale="en" hasCookie>{ui}</LocaleProvider>);
}

describe("export scope labels", () => {
  // `t` is injected, so these assert the MAPPING — which protocol string means
  // which label — without pinning the test to one language. The catalogue is
  // exercised through the rendered rows below.
  const vi = (k: string) => viMessages[k as keyof typeof viMessages] as string;
  const en = (k: string) => enMessages[k as keyof typeof enMessages] as string;

  test("turns chapter protocol scopes into student-facing names", () => {
    expect(formatExportScope("chapter:intro|lit_review|methodology", vi)).toBe("Chương 1–3");
    expect(formatExportScope("chapter:methodology", vi)).toBe("Chương 3");
    expect(formatExportScope("full", vi)).toBe("Toàn bộ luận văn");
  });

  test("and does it in English too — these were hardcoded Vietnamese", () => {
    expect(formatExportScope("chapter:intro|lit_review|methodology", en)).toBe("Chapters 1–3");
    expect(formatExportScope("full", en)).toBe("Full thesis");
    expect(formatExportScope("M1,M2", en)).toBe("M1 · Topic + M2 · Literature");
  });

  test("an unknown scope falls through to the backend string", () => {
    expect(formatExportScope("M9", en)).toBe("M9");
    expect(formatExportScope("chapter:appendix", en)).toBe("appendix");
    expect(formatExportScope("", en)).toBe("Document");
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
    triggerExportDownload.mockReset();
    triggerExportDownload.mockResolvedValue(undefined);
    exportViewUrl.mockReset();
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

  test("an Outputs row opens the same viewer, and still downloads from its own button", async () => {
    // Outputs used to be download-only: the only way to see whether an export
    // was any good was to save it and open Word. Same reasoning as the Context
    // rows below — and the same modal, so there is one docx/pdf viewer.
    exportViewUrl.mockImplementation(() => new Promise<string>(() => {}));
    renderEn(<ExportRowItem row={{
      id: "e1", scope: "full", kind: "docx", filename: "thesis-abc.docx",
      size_bytes: 195_000, created_at: "2026-09-11",
      download_url: "/api/v1/projects/p1/exports/thesis-abc.docx",
    }} />);

    // Named by scope, not the storage filename ("thesis-abc.docx" tells the
    // student nothing). Both row buttons carry that label — [0] opens it,
    // [1] saves it. Rendered under the "en" provider, so the scope reads in
    // English: it used to be hardcoded Vietnamese here.
    const row = () => screen.getAllByRole("button", { name: /DOCX · Full thesis/ });
    fireEvent.click(row()[0]);
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(triggerExportDownload).not.toHaveBeenCalled();

    fireEvent.click(row()[1]);
    expect(triggerExportDownload).toHaveBeenCalledWith(
      "/api/v1/projects/p1/exports/thesis-abc.docx");
  });

  test("the preview overlay escapes the panel column and lands on <body>", () => {
    // ChatShellLayout gives the right pane `lg:translate-x-0` (it slides in as
    // a drawer on mobile). A transform — even a zero one — makes that pane the
    // containing block for `position: fixed` descendants, so the modal's
    // `fixed inset-0` covered the ~340px panel instead of the viewport: the
    // student got a sliver of dimmed sidebar with their document crushed into
    // it. Portalling is the fix, so assert the DOM position, not the classes.
    const { container } = _panelWithDocx();
    fireEvent.click(screen.getByRole("button", { name: `Preview ${DOCX.filename}` }));
    const dialog = screen.getByRole("dialog", { name: DOCX.filename });
    expect(container.contains(dialog)).toBe(false);
    expect(dialog.parentElement).toBe(document.body);
  });
});
