import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { SWRConfig } from "swr";

import { LocaleProvider } from "@/app/lib/i18n/LocaleProvider";
import { SourcesRail } from "../SourcesRail";


// "en" pinned so these keep asserting behaviour rather than the Vietnamese
// wording, and a FRESH SWR cache per render — the key is the same URL in every
// test, so one test's references were being served to the next.
function renderEn(ui: React.ReactElement) {
  return render(
    <LocaleProvider initialLocale="en" hasCookie>
      <SWRConfig value={{ provider: () => new Map() }}>{ui}</SWRConfig>
    </LocaleProvider>,
  );
}


beforeEach(() => {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ([
      { id: "r1", author: "Smith", year: "2024" },
      { id: "r2", author: "Jones", year: "2023" },
    ]),
  });
});
afterEach(() => vi.restoreAllMocks());


describe("SourcesRail", () => {
  it("renders M2 references", async () => {
    renderEn(<SourcesRail projectId="p1" />);
    await waitFor(() => expect(screen.getByText(/Smith/)).toBeInTheDocument());
    expect(screen.getByText(/Jones/)).toBeInTheDocument();
  });

  it("shows count in header", async () => {
    renderEn(<SourcesRail projectId="p1" />);
    await waitFor(() => expect(screen.getByText(/Sources \(2\)/i)).toBeInTheDocument());
  });

  it("highlights the source matching highlightedId (citation click target)", async () => {
    const { container } = renderEn(<SourcesRail projectId="p1" highlightedId="r2" />);
    await waitFor(() => expect(screen.getByText(/Jones/)).toBeInTheDocument());
    const highlighted = container.querySelector('[aria-current="true"]');
    expect(highlighted?.id).toBe("src-r2");
    // The non-highlighted source is not marked current.
    expect(container.querySelector("#src-r1")?.getAttribute("aria-current")).toBeNull();
  });
});


describe("opening a source", () => {
  function _mock(refs: any[]) {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => refs });
  }

  it("links to the paper, in a new tab", async () => {
    // The endpoint returns the whole paper, so `url` was already on the wire —
    // the rail dropped it, and checking a source meant copying the title into
    // a search engine.
    _mock([{ id: "r1", author: "Buhalis", year: "2023",
             url: "https://doi.org/10.1016/j.tourman.2023.104724" }]);
    renderEn(<SourcesRail projectId="p1" />);

    const link = await screen.findByRole("link");
    expect(link).toHaveAttribute("href", "https://doi.org/10.1016/j.tourman.2023.104724");
    // The editor holds unsaved prose — navigating THIS tab away is the one
    // thing this rail must not do.
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  it("resolves a bare DOI through doi.org", async () => {
    _mock([{ id: "r1", author: "Akram", year: "2026", doi: "10.70310/jrt.2026.030212111" }]);
    renderEn(<SourcesRail projectId="p1" />);
    expect(await screen.findByRole("link"))
      .toHaveAttribute("href", "https://doi.org/10.70310/jrt.2026.030212111");
  });

  it("does not double-prefix a DOI that is already a URL", async () => {
    _mock([{ id: "r1", author: "X", year: "2020", doi: "https://doi.org/10.1/abc" }]);
    renderEn(<SourcesRail projectId="p1" />);
    expect(await screen.findByRole("link")).toHaveAttribute("href", "https://doi.org/10.1/abc");
  });

  it("renders a source with no identifier as plain text, not a dead link", async () => {
    _mock([{ id: "r1", author: "Anon", year: "2019", title: "Untraceable" }]);
    renderEn(<SourcesRail projectId="p1" />);
    await screen.findByText(/Anon/);
    expect(screen.queryByRole("link")).toBeNull();
  });
});
