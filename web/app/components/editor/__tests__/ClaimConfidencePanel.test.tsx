import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ClaimConfidencePanel } from "../ClaimConfidencePanel";

const suggestion = (status: "pending" | "accepted" | "rejected" = "pending") => ({
  id: "s1", chapter: "intro", anchor: { from_offset: 0, to_offset: 12, old_text: "Một claim cần nguồn." },
  classification: "unsupported", rationale_vi: "Claim này cần bằng chứng trực tiếp.", proposed_text: "Một claim cần nguồn (Nguyễn, 2024).",
  source: { id: "r1", title: "Nguồn minh hoạ", authors: ["Nguyễn A."], year: 2024, doi: "10.1/example", verified: true, provider: "Crossref" },
  evidence: { kind: "abstract", text: "Đoạn tóm tắt hỗ trợ claim.", relation: "supports", source_url: "https://example.test/evidence" }, status, actionable: true,
});
const billing = (overrides: Partial<{ credits_charged: number; credits_limit: number; prompt_tokens: number; completion_tokens: number; credit_balance: number }> = {}) => ({
  credits_charged: 3, credits_limit: 20, prompt_tokens: 120, completion_tokens: 30, credit_balance: 97, ...overrides,
});
const running = (completed = 0, billingData = billing()) => ({ review_id: "r1", status: completed >= 2 ? "completed" : "running", chunks_total: 2, chunks_completed: completed, suggestions: [suggestion()], warnings: [], coverage: { chars_total: 100, chars_processed: completed * 50, claims_total: 2, claims_assessed: completed, claims_unresolved: 0 }, sources_verified_unique: 1, billing: billingData });

beforeEach(() => { global.fetch = vi.fn(); });
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });
const response = (data: unknown) => ({ ok: true, json: async () => data });

function panel(props: any = {}) {
  const onFlush = props.onFlush ?? vi.fn().mockResolvedValue(undefined);
  const onAccepted = props.onAccepted ?? vi.fn();
  return { onFlush, onAccepted, ...render(<ClaimConfidencePanel projectId="p1" onBack={vi.fn()} onFlush={onFlush} onAccepted={onAccepted} {...props} />) };
}

describe("ClaimConfidencePanel", () => {
  it("flushes then processes one chunk at a time and renders source evidence", async () => {
    (global.fetch as any)
      .mockResolvedValueOnce(response({ review: null }))
      .mockResolvedValueOnce(response(running(0)))
      .mockResolvedValueOnce(response(running(1)))
      .mockResolvedValueOnce(response(running(2)));
    const view = panel();
    expect(await screen.findByRole("button", { name: /Bắt đầu đánh giá/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Bắt đầu đánh giá/i }));
    expect(await screen.findByText("Nguồn minh hoạ")).toBeInTheDocument();
    expect(view.onFlush).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/2\/2 đoạn/)).toBeInTheDocument();
    expect(screen.getByText("Đoạn tóm tắt hỗ trợ claim.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Xem bằng chứng/i })).toHaveAttribute("href", "https://example.test/evidence");
  });

  it("accepts only after flush, applies returned chapter data, and updates cumulative review", async () => {
    (global.fetch as any)
      .mockResolvedValueOnce(response({ review: running(2) }))
      .mockResolvedValueOnce(response({ chapter_name: "intro", chapter: { prose: "Nội dung đã cập nhật.", document_fingerprint: "fp2" }, suggestion_id: "s1", status: "accepted", review: { ...running(2), suggestions: [suggestion("accepted")] } }));
    const view = panel();
    expect(await screen.findByRole("button", { name: "Chấp nhận" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Chấp nhận" }));
    await waitFor(() => expect(view.onAccepted).toHaveBeenCalledWith(expect.objectContaining({ chapterName: "intro", prose: "Nội dung đã cập nhật.", documentFingerprint: "fp2" })));
    expect(view.onFlush).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Đã chấp nhận")).toBeInTheDocument();
  });

  it("resumes a latest running review without starting a new one", async () => {
    (global.fetch as any)
      .mockResolvedValueOnce(response({ review: running(0) }))
      .mockResolvedValueOnce(response(running(1)))
      .mockResolvedValueOnce(response(running(2)));
    panel();
    expect(await screen.findByRole("button", { name: "Tiếp tục" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Tiếp tục" }));
    await screen.findByText(/2\/2 đoạn/);
    expect((global.fetch as any).mock.calls.filter((call: any[]) => String(call[0]).includes("/start"))).toHaveLength(0);
  });

  it("does not start twice while flushing and drops a response after the project changes", async () => {
    let releaseFlush: (() => void) | undefined;
    const onFlush = vi.fn(() => new Promise<void>(resolve => { releaseFlush = resolve; }));
    (global.fetch as any).mockResolvedValueOnce(response({ review: null }));
    const view = panel({ onFlush, projectId: "double-start" });
    const start = await screen.findByRole("button", { name: /Bắt đầu đánh giá/i });
    fireEvent.click(start); fireEvent.click(start);
    expect(onFlush).toHaveBeenCalledTimes(1);
    view.rerender(<ClaimConfidencePanel projectId="p2" onBack={vi.fn()} onFlush={onFlush} onAccepted={vi.fn()} />);
    releaseFlush?.();
    await waitFor(() => expect((global.fetch as any).mock.calls.filter((call: any[]) => String(call[0]).includes("/start"))).toHaveLength(0));
  });

  it("sends the bounded credit budget and shows actual usage without claiming a hard cap", async () => {
    (global.fetch as any)
      .mockResolvedValueOnce(response({ review: null }))
      .mockResolvedValueOnce(response(running(0, billing({ credits_limit: 500 }))))
      .mockResolvedValueOnce(response(running(1, billing({ credits_limit: 500 }))))
      .mockResolvedValueOnce(response(running(2, billing({ credits_limit: 500 }))));
    panel({ projectId: "billing-budget" });

    const input = await screen.findByRole("spinbutton", { name: "Giới hạn credit" });
    expect(input).toHaveValue(20);
    fireEvent.change(input, { target: { value: "999" } });
    expect(input).toHaveValue(500);
    fireEvent.click(screen.getByRole("button", { name: /Bắt đầu đánh giá/i }));

    await screen.findByText(/Đã dùng 3 \/ 500 credit · 150 token/);
    const startCall = (global.fetch as any).mock.calls.find((call: any[]) => String(call[0]).includes("/m5/claims/start"));
    expect(JSON.parse(startCall[1].body)).toMatchObject({ credit_limit: 500 });
    expect(screen.getByText(/lượt đang chạy có thể hoàn tất sau ngưỡng/i)).toBeInTheDocument();
    expect(screen.getByText(/bộ nhớ đệm/i)).toBeInTheDocument();
  });

  it("updates a paused review budget without restarting or processing another đoạn", async () => {
    (global.fetch as any)
      .mockResolvedValueOnce(response({ review: running(0, billing({ credits_limit: 20 })) }))
      .mockResolvedValueOnce(response(running(0, billing({ credits_limit: 75 }))));
    panel({ projectId: "paused-budget" });

    const input = await screen.findByRole("spinbutton", { name: "Giới hạn credit" });
    expect(input).toHaveValue(20);
    fireEvent.change(input, { target: { value: "75" } });
    fireEvent.click(screen.getByRole("button", { name: "Cập nhật ngưỡng" }));

    await screen.findByText(/Đã dùng 3 \/ 75 credit · 150 token/);
    const budgetCall = (global.fetch as any).mock.calls.find((call: any[]) => String(call[0]).includes("/claims/r1/budget"));
    expect(budgetCall[1].method).toBe("POST");
    expect(JSON.parse(budgetCall[1].body)).toMatchObject({ credit_limit: 75 });
    expect((global.fetch as any).mock.calls.filter((call: any[]) => String(call[0]).includes("/start") || String(call[0]).includes("/next"))).toHaveLength(0);
  });
});


  it("polls real activity while a chunk is pending and cleans the timer on unmount", async () => {
    let releaseNext: (() => void) | undefined;
    const pendingNext = new Promise(resolve => { releaseNext = () => resolve(running(1)); });
    (global.fetch as any)
      .mockResolvedValueOnce(response({ review: null }))
      .mockResolvedValueOnce(response(running(0)))
      .mockReturnValueOnce(pendingNext)
      .mockResolvedValueOnce(response({ review_id: "r1", status: "running", activities: [
        { stage: "analyzing" }, { stage: "searching", query: "tourism trust evidence" },
      ] }));
    const view = panel({ projectId: "progress-live" });
    const start = await screen.findByRole("button", { name: /Bắt đầu đánh giá/i });
    vi.useFakeTimers();
    fireEvent.click(start);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect((global.fetch as any).mock.calls.some((call: any[]) => String(call[0]).includes("/next"))).toBe(true);
    await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });
    expect(await screen.findByText(/tourism trust evidence/)).toBeInTheDocument();
    expect(screen.getByLabelText("Đang xử lý")).toBeInTheDocument();
    const callsBeforeUnmount = (global.fetch as any).mock.calls.length;
    view.unmount();
    await act(async () => { await vi.advanceTimersByTimeAsync(2_000); });
    expect((global.fetch as any).mock.calls).toHaveLength(callsBeforeUnmount);
    releaseNext?.();
  });
