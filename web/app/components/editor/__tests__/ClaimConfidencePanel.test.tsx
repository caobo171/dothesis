import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ClaimConfidencePanel } from "../ClaimConfidencePanel";

const suggestion = (status: "pending" | "accepted" | "rejected" = "pending") => ({
  id: "s1", chapter: "intro", anchor: { from_offset: 0, to_offset: 12, old_text: "Một claim cần nguồn." },
  classification: "unsupported", rationale_vi: "Claim này cần bằng chứng trực tiếp.", proposed_text: "Một claim cần nguồn (Nguyễn, 2024).",
  source: { id: "r1", title: "Nguồn minh hoạ", authors: ["Nguyễn A."], year: 2024, doi: "10.1/example", verified: true, provider: "Crossref" },
  evidence: { kind: "abstract", text: "Đoạn tóm tắt hỗ trợ claim.", relation: "supports", source_url: "https://example.test/evidence" }, status, actionable: true,
});
const billing = (overrides: Partial<{ credits_charged: number; credits_limit: number; prompt_tokens: number; completion_tokens: number; credit_balance: number; pending_calls: number }> = {}) => ({
  credits_charged: 3, credits_limit: 20, prompt_tokens: 120, completion_tokens: 30, credit_balance: 97, ...overrides,
});
const running = (completed = 0, billingData = billing()) => ({ review_id: "r1", status: completed >= 2 ? "completed" : "running", chunks_total: 2, chunks_completed: completed, suggestions: [suggestion()], warnings: [], coverage: { chars_total: 100, chars_processed: completed * 50, claims_total: 2, claims_assessed: completed, claims_unresolved: 0 }, sources_verified_unique: 1, billing: billingData });

beforeEach(() => { global.fetch = vi.fn(); });
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });
const response = (data: unknown) => ({ ok: true, json: async () => data });
const failedResponse = (status: number, code: string, message: string, retryable?: boolean, metadata: Record<string, unknown> = {}) => ({
  ok: false, status, json: async () => ({ detail: { error: { code, message, ...(retryable === undefined ? {} : { retryable }), ...metadata } } }),
});

function panel(props: any = {}) {
  const onFlush = props.onFlush ?? vi.fn().mockResolvedValue(undefined);
  const onAccepted = props.onAccepted ?? vi.fn();
  return { onFlush, onAccepted, ...render(<ClaimConfidencePanel projectId="p1" onBack={vi.fn()} onFlush={onFlush} onAccepted={onAccepted} {...props} />) };
}

describe("ClaimConfidencePanel", () => {
  it("flushes then processes one chunk at a time and renders the review summary", async () => {
    (global.fetch as any)
      .mockResolvedValueOnce(response({ review: null }))
      .mockResolvedValueOnce(response(running(0)))
      .mockResolvedValueOnce(response(running(1)))
      .mockResolvedValueOnce(response(running(2)));
    const view = panel();
    expect(await screen.findByRole("button", { name: /Bắt đầu đánh giá/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Bắt đầu đánh giá/i }));
    expect(await screen.findByRole("button", { name: /Xem đề xuất trong bài/i })).toBeInTheDocument();
    expect(view.onFlush).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/2\/2 đoạn/)).toBeInTheDocument();
    expect(screen.getByText("Chưa có bằng chứng")).toBeInTheDocument();
    expect(screen.getByText("Tất cả đề xuất")).toBeInTheDocument();
  });

  it("opens the first pending suggestion in the editor", async () => {
    (global.fetch as any).mockResolvedValueOnce(response({ review: running(2) }));
    const onSelectChapter = vi.fn();
    panel({ onSelectChapter });
    fireEvent.click(await screen.findByRole("button", { name: /Xem đề xuất trong bài/i }));
    expect(onSelectChapter).toHaveBeenCalledWith("intro");
  });

  it("shows failed evidence assessments without claiming the completed scan assessed them", async () => {
    const failed = {
      ...running(2),
      coverage: { chars_total: 100, chars_processed: 100, claims_total: 2, claims_assessed: 1, claims_unresolved: 1, claims_failed: 1 },
      suggestions: [{ ...suggestion(), classification: "assessment_failed", proposed_text: null, source: null, evidence: null, actionable: false,
        rationale_vi: "Chưa đánh giá được nhận định này: Trích dẫn bằng chứng không khớp nguyên văn nguồn đã truy xuất. Hệ thống không tạo đề xuất trích dẫn." }],
    };
    (global.fetch as any).mockResolvedValueOnce(response({ review: failed }));
    panel({ projectId: "failed-assessment" });
    expect(await screen.findByText("Chưa thể xác minh")).toBeInTheDocument();
    expect(screen.getByText(/Đã quét 2\/2 đoạn/)).toBeInTheDocument();
    expect(screen.getByText(/1 chưa đánh giá được/)).toBeInTheDocument();
    expect(screen.getByText("Tất cả đề xuất")).toBeInTheDocument();
  });

  it("explains that an unverified source was already excluded and needs no action", async () => {
    const reviewed = { ...running(2), warnings: ["Một nguồn chưa xác minh được metadata; không tự động đề xuất chèn citation từ nguồn này."] };
    (global.fetch as any).mockResolvedValueOnce(response({ review: reviewed }));
    panel({ projectId: "friendly-warning" });
    expect(await screen.findByText("Nguồn thiếu thông tin đã được tự động loại")).toBeInTheDocument();
    expect(screen.getByText(/Bạn không cần làm gì/)).toBeInTheDocument();
    expect(screen.getByText(/không xuất hiện trong các đề xuất có thể chấp nhận/)).toBeInTheDocument();
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

  it("retries one retryable chunk once and continues from the same checkpoint", async () => {
    vi.useFakeTimers();
    let nextCalls = 0;
    (global.fetch as any).mockImplementation((url: string) => {
      if (url.includes("/latest")) return Promise.resolve(response({ review: null }));
      if (url.includes("/start")) return Promise.resolve(response(running(0)));
      if (url.includes("/progress")) return Promise.resolve(response({ review_id: "r1", status: "running", activities: [] }));
      if (url.includes("/next")) {
        nextCalls += 1;
        if (nextCalls === 1) return Promise.resolve(failedResponse(503, "claim_review_failed", "Mô hình trả về dữ liệu không hợp lệ; đoạn chưa được đánh giá.", true));
        return Promise.resolve(response(running(nextCalls === 2 ? 1 : 2)));
      }
      throw new Error(`Unexpected ${url}`);
    });
    panel({ projectId: "retry-once" });
    fireEvent.click(await screen.findByRole("button", { name: /Bắt đầu đánh giá/i }));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(await screen.findByText(/Đang thử lại đoạn 1 \(1\/1\)/)).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(2_000); });
    await screen.findByText(/2\/2 đoạn/);
    expect(nextCalls).toBe(3);
  });

  it("stops after the second retryable failure and labels it as an error", async () => {
    vi.useFakeTimers();
    let nextCalls = 0;
    (global.fetch as any).mockImplementation((url: string) => {
      if (url.includes("/latest")) return Promise.resolve(response({ review: null }));
      if (url.includes("/start")) return Promise.resolve(response(running(0)));
      if (url.includes("/progress")) return Promise.resolve(response({ review_id: "r1", status: "running", activities: [] }));
      if (url.includes("/next")) {
        nextCalls += 1;
        return Promise.resolve(failedResponse(503, "claim_review_failed", "Lượt kiểm tra đã hết thời gian chờ; đoạn chưa được đánh giá.", true));
      }
      throw new Error(`Unexpected ${url}`);
    });
    panel({ projectId: "retry-stops" });
    fireEvent.click(await screen.findByRole("button", { name: /Bắt đầu đánh giá/i }));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    await screen.findByText(/Đang thử lại đoạn 1 \(1\/1\)/);
    await act(async () => { await vi.advanceTimersByTimeAsync(2_000); });
    expect(await screen.findByText(/Đã dừng do lỗi 0\/2 đoạn/)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/hết thời gian chờ/i);
    expect(nextCalls).toBe(2);
  });

  it("does not retry a credit checkpoint rejection", async () => {
    let nextCalls = 0;
    (global.fetch as any).mockImplementation((url: string) => {
      if (url.includes("/latest")) return Promise.resolve(response({ review: null }));
      if (url.includes("/start")) return Promise.resolve(response(running(0)));
      if (url.includes("/progress")) return Promise.resolve(response({ review_id: "r1", status: "running", activities: [] }));
      if (url.includes("/next")) {
        nextCalls += 1;
        return Promise.resolve(failedResponse(402, "claim_review_budget", "Đã đạt ngưỡng tín dụng."));
      }
      throw new Error(`Unexpected ${url}`);
    });
    panel({ projectId: "budget-no-retry" });
    fireEvent.click(await screen.findByRole("button", { name: /Bắt đầu đánh giá/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Đã chạm ngưỡng credit/i);
    expect(nextCalls).toBe(1);
  });

  it("cancels the scheduled retry when the user stops", async () => {
    vi.useFakeTimers();
    let nextCalls = 0;
    (global.fetch as any).mockImplementation((url: string) => {
      if (url.includes("/latest")) return Promise.resolve(response({ review: null }));
      if (url.includes("/start")) return Promise.resolve(response(running(0)));
      if (url.includes("/progress")) return Promise.resolve(response({ review_id: "r1", status: "running", activities: [] }));
      if (url.includes("/next")) {
        nextCalls += 1;
        return Promise.resolve(failedResponse(503, "claim_review_failed", "Mô hình trả về dữ liệu không hợp lệ; đoạn chưa được đánh giá.", true));
      }
      throw new Error(`Unexpected ${url}`);
    });
    panel({ projectId: "retry-cancel" });
    fireEvent.click(await screen.findByRole("button", { name: /Bắt đầu đánh giá/i }));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    await screen.findByText(/Đang thử lại đoạn 1 \(1\/1\)/);
    fireEvent.click(screen.getByRole("button", { name: /Dừng sau đoạn này/i }));
    await act(async () => { await vi.advanceTimersByTimeAsync(2_000); });
    expect(nextCalls).toBe(1);
  });

  it("waits read-only for a pending billing receipt, then resumes the same checkpoint", async () => {
    vi.useFakeTimers();
    let nextCalls = 0;
    let progressCalls = 0;
    (global.fetch as any).mockImplementation((url: string) => {
      if (url.includes("/latest")) return Promise.resolve(response({ review: null }));
      if (url.includes("/start")) return Promise.resolve(response(running(0)));
      if (url.includes("/next")) {
        nextCalls += 1;
        if (nextCalls === 1) return Promise.resolve(failedResponse(409, "claim_review_pending", "Lượt gọi trước vẫn đang hoàn tất."));
        return Promise.resolve(response(running(nextCalls === 2 ? 1 : 2)));
      }
      if (url.includes("/progress")) {
        progressCalls += 1;
        return Promise.resolve(response({ review_id: "r1", status: "running", activities: [], billing: billing({ pending_calls: progressCalls < 3 ? 1 : 0 }) }));
      }
      throw new Error(`Unexpected ${url}`);
    });
    panel({ projectId: "pending-receipt" });
    fireEvent.click(await screen.findByRole("button", { name: /Bắt đầu đánh giá/i }));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); });
    expect(await screen.findByText(/Đang chờ mô hình hoàn tất/i)).toBeInTheDocument();
    expect(nextCalls).toBe(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(3_000); });
    await screen.findByText(/2\/2 đoạn/);
    expect(nextCalls).toBe(3);
    expect(progressCalls).toBeGreaterThanOrEqual(3);
  });

  it("waits for a pending receipt after a timeout response instead of scheduling a model retry", async () => {
    vi.useFakeTimers();
    let nextCalls = 0;
    let progressCalls = 0;
    (global.fetch as any).mockImplementation((url: string) => {
      if (url.includes("/latest")) return Promise.resolve(response({ review: null }));
      if (url.includes("/start")) return Promise.resolve(response(running(0)));
      if (url.includes("/next")) {
        nextCalls += 1;
        if (nextCalls === 1) return Promise.resolve(failedResponse(503, "claim_review_failed", "Lượt kiểm tra đã hết thời gian chờ.", true, { kind: "timeout" }));
        return Promise.resolve(response(running(2)));
      }
      if (url.includes("/progress")) {
        progressCalls += 1;
        return Promise.resolve(response({ review_id: "r1", status: "running", activities: [], billing: billing({ pending_calls: progressCalls === 1 ? 1 : 0 }) }));
      }
      throw new Error(`Unexpected ${url}`);
    });
    panel({ projectId: "timeout-pending-receipt" });
    fireEvent.click(await screen.findByRole("button", { name: /Bắt đầu đánh giá/i }));
    await screen.findByText(/2\/2 đoạn/);
    expect(nextCalls).toBe(2);
    expect(progressCalls).toBe(2);
  });

  it("stops a pending billing wait without issuing another next request", async () => {
    vi.useFakeTimers();
    let nextCalls = 0;
    (global.fetch as any).mockImplementation((url: string) => {
      if (url.includes("/latest")) return Promise.resolve(response({ review: null }));
      if (url.includes("/start")) return Promise.resolve(response(running(0)));
      if (url.includes("/next")) {
        nextCalls += 1;
        return Promise.resolve(failedResponse(409, "claim_review_pending", "Lượt gọi trước vẫn đang hoàn tất."));
      }
      if (url.includes("/progress")) return Promise.resolve(response({ review_id: "r1", status: "running", activities: [], billing: billing({ pending_calls: 1 }) }));
      throw new Error(`Unexpected ${url}`);
    });
    panel({ projectId: "pending-stop" });
    fireEvent.click(await screen.findByRole("button", { name: /Bắt đầu đánh giá/i }));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); });
    await screen.findByText(/Đang chờ mô hình hoàn tất/i);
    fireEvent.click(screen.getByRole("button", { name: /Dừng sau đoạn này/i }));
    await act(async () => { await vi.advanceTimersByTimeAsync(6_000); });
    expect(nextCalls).toBe(1);
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
