import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ReviewPanel } from "../ReviewPanel";
import { tokenStore } from "@/app/lib/tokenStore";

const review = (kind = "claim_confidence", id = "one") => ({
  overall: 7.5, method: "rubric", dimensions: [{ name: "citations", score: 0.7, weight: 1, findings: [] }],
  blocking: [], reviewed_at: "2026-09-16T00:00:00Z", review_id: id, review_kind: kind,
});

beforeEach(() => { global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => review() }); });
afterEach(() => vi.restoreAllMocks());

describe("ReviewPanel", () => {
  it("shows the quoted evidence without duplicating findings as generic questions", async () => {
    (global.fetch as any).mockResolvedValueOnce({ ok: true, json: async () => ({
      ...review(), dimensions: [{ name: "coherence", score: 0.7, weight: 1, findings: [{
        issue: "H1: hệ số trong bài chưa khớp.", fix: "Đối chiếu bảng kết quả.", chapter: "results", severity: "hard",
        evidence: { sentence: "ATT → INT: β = 0,8." },
      }] }],
    }) });
    render(<ReviewPanel projectId="quoted-evidence" />);
    fireEvent.click(screen.getAllByRole("button", { name: /Run review/i })[0]);
    expect(await screen.findByText("ATT → INT: β = 0,8.")).toBeInTheDocument();
    expect(screen.getByText("Câu cần đối chiếu")).toBeInTheDocument();
    expect(screen.queryByText("Câu hỏi cho tác giả")).not.toBeInTheDocument();
    expect(screen.queryByText(/Bạn sẽ xử lý vấn đề/)).not.toBeInTheDocument();
  });

  it("makes View results the completed card's primary action", async () => {
    render(<ReviewPanel projectId="primary-action" />);
    fireEvent.click(screen.getAllByRole("button", { name: /Run review/i })[0]);
    await screen.findByText("75");
    fireEvent.click(screen.getByRole("button", { name: /Tất cả review/i }));
    expect(screen.getByRole("button", { name: "View results" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run again" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Run review/i })).toHaveLength(4);
    fireEvent.click(screen.getByRole("button", { name: "View results" }));
    expect(await screen.findByText("75")).toBeInTheDocument();
  });

  it("keeps the previous result visible when a rerun fails", async () => {
    render(<ReviewPanel projectId="rerun-failure" />);
    fireEvent.click(screen.getAllByRole("button", { name: /Run review/i })[0]);
    await screen.findByText("75");
    (global.fetch as any).mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({}) });
    fireEvent.click(screen.getByRole("button", { name: /Chạy lại/i }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/Kết quả trước đó vẫn được giữ/i));
    expect(screen.getByText("75")).toBeInTheDocument();
  });

  it("restores a project's review results after the panel remounts", async () => {
    const first = render(<ReviewPanel projectId="remount-cache" />);
    fireEvent.click(screen.getAllByRole("button", { name: /Run review/i })[0]);
    await screen.findByText("75");
    first.unmount();

    render(<ReviewPanel projectId="remount-cache" />);
    expect(screen.getByRole("button", { name: "View results" })).toBeInTheDocument();
  });

  it("keeps cached results isolated to their project", async () => {
    const first = render(<ReviewPanel projectId="project-a" />);
    fireEvent.click(screen.getAllByRole("button", { name: /Run review/i })[0]);
    await screen.findByText("75");
    first.unmount();

    render(<ReviewPanel projectId="project-b" />);
    expect(screen.queryByRole("button", { name: "View results" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Run review/i })).toHaveLength(5);
  });

  it("drops a late response after the project changes", async () => {
    let resolveReview: ((value: unknown) => void) | undefined;
    (global.fetch as any).mockImplementationOnce(() => new Promise(resolve => { resolveReview = resolve; }));
    const panel = render(<ReviewPanel projectId="late-project-a" />);
    fireEvent.click(screen.getAllByRole("button", { name: /Run review/i })[0]);
    panel.rerender(<ReviewPanel projectId="late-project-b" />);

    await act(async () => {
      resolveReview?.({ ok: true, json: async () => review() });
    });

    await waitFor(() => expect(screen.queryByRole("button", { name: "View results" })).not.toBeInTheDocument());
    expect(screen.getAllByRole("button", { name: /Run review/i })).toHaveLength(5);
  });

  it("does not expose a late response after the active account changes", async () => {
    let token = "account-a";
    vi.spyOn(tokenStore, "get").mockImplementation(() => token);
    let resolveReview: ((value: unknown) => void) | undefined;
    (global.fetch as any).mockImplementationOnce(() => new Promise(resolve => { resolveReview = resolve; }));
    render(<ReviewPanel projectId="late-account" />);
    fireEvent.click(screen.getAllByRole("button", { name: /Run review/i })[0]);
    token = "account-b";

    await act(async () => {
      resolveReview?.({ ok: true, json: async () => review() });
    });

    await waitFor(() => expect(screen.queryByRole("button", { name: "View results" })).not.toBeInTheDocument());
  });
});
