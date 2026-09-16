"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, ArrowLeft, Check, ChevronLeft, ChevronRight, ExternalLink, FileSearch, Loader2, Pause, Play, RotateCcw, X } from "lucide-react";

import { ApiError, apiFetch } from "@/app/lib/api";
import { tokenStore } from "@/app/lib/tokenStore";
import type { ChapterName } from "./OutlineRail";

export type ClaimAcceptedChapter = {
  revision: string;
  chapterName: ChapterName;
  prose: string;
  documentFingerprint?: string;
};

type Source = { id: string; title: string; authors?: string[]; year?: string | number; doi?: string; url?: string; verified?: boolean; provider?: string; venue?: string };
type Evidence = { kind: "abstract" | "full_text"; text: string; source_url?: string; relation: "supports" | "partial" | "contradicts" | "irrelevant" };
type Suggestion = {
  id: string; chapter: ChapterName; anchor: { from_offset: number; to_offset: number; old_text: string; document_fingerprint?: string };
  classification: string; rationale_vi: string; proposed_text: string | null; source: Source | null; evidence: Evidence | null;
  status: "pending" | "accepted" | "rejected" | "stale"; actionable: boolean;
};
type Review = {
  review_id: string; status: "running" | "completed"; chunks_total: number; chunks_completed: number; suggestions: Suggestion[]; warnings: string[];
  coverage: { chars_total: number; chars_processed: number; claims_total: number; claims_assessed: number; claims_unresolved: number };
  sources_verified_unique: number;
  credit_limit?: number;
  billing?: Billing;
};
type Billing = { credits_charged: number; credits_limit: number; prompt_tokens: number; completion_tokens: number; credit_balance: number };
type ClaimProgress = {
  review_id: string; status: "running" | "completed";
  activities: Array<{ stage: string; query?: string; count?: number; at?: string }>;
  billing?: Billing;
};

const CLAIM_CACHE_LIMIT = 6;
const claimSessionCache = new Map<string, Review>();
const cacheKey = (projectId: string) => `${tokenStore.get() ?? "anonymous"}:${projectId}`;
const safeUrl = (value?: string) => value && /^https?:\/\//i.test(value) ? value : undefined;
const reviewCreditLimit = (review?: Review | null) => review?.credit_limit ?? review?.billing?.credits_limit;
const labels: Record<string, string> = {
  citation_opportunity: "Bổ sung nguồn", supported: "Đã có nguồn hỗ trợ", partial_support: "Bằng chứng một phần", needs_source: "Chưa tìm được nguồn",
  unsupported: "Chưa có bằng chứng", weakly_supported: "Hỗ trợ một phần", misrepresented: "Diễn giải chưa đúng",
  overstated: "Khẳng định quá mức", contradicted: "Mâu thuẫn", unverifiable: "Chưa thể xác minh",
};
const evidenceLabels: Record<Evidence["relation"], string> = { supports: "Hỗ trợ", partial: "Hỗ trợ một phần", contradicts: "Mâu thuẫn", irrelevant: "Không liên quan" };
const chapterLabels: Record<string, string> = { intro: "Mở đầu", lit_review: "Tổng quan tài liệu", methodology: "Phương pháp", results: "Kết quả", conclusion: "Kết luận" };

export function ClaimConfidencePanel({ projectId, onBack, onFlush, onAccepted, onSelectChapter }: {
  projectId: string;
  onBack: () => void;
  onFlush: () => Promise<void>;
  onAccepted: (chapter: ClaimAcceptedChapter) => void;
  onSelectChapter?: (chapter: ChapterName) => void;
}) {
  const [review, setReview] = useState<Review | null>(() => claimSessionCache.get(cacheKey(projectId)) ?? null);
  const [loadingLatest, setLoadingLatest] = useState(true);
  const [running, setRunning] = useState(false);
  const [stopRequested, setStopRequested] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [progress, setProgress] = useState<ClaimProgress | null>(null);
  const [creditLimit, setCreditLimit] = useState(20);
  const [budgetUpdating, setBudgetUpdating] = useState(false);
  const projectRef = useRef(projectId);
  const requestRef = useRef(0);
  const stopRef = useRef(false);
  const operationRef = useRef(false);
  const operationVersionRef = useRef(0);
  const decisionRef = useRef(false);
  const budgetUpdateRef = useRef(false);

  const saveReview = useCallback((next: Review, requestProject = projectId, key = cacheKey(projectId)) => {
    if (projectRef.current !== requestProject || cacheKey(requestProject) !== key) return false;
    claimSessionCache.delete(key); claimSessionCache.set(key, next);
    while (claimSessionCache.size > CLAIM_CACHE_LIMIT) {
      const oldest = claimSessionCache.keys().next().value;
      if (oldest === undefined) break;
      claimSessionCache.delete(oldest);
    }
    const nextCreditLimit = reviewCreditLimit(next);
    if (typeof nextCreditLimit === "number") setCreditLimit(nextCreditLimit);
    setReview(next);
    return true;
  }, [projectId]);

  useEffect(() => {
    projectRef.current = projectId;
    requestRef.current += 1;
    stopRef.current = true;
    operationVersionRef.current += 1;
    operationRef.current = false;
    const cachedReview = claimSessionCache.get(cacheKey(projectId)) ?? null;
    setReview(cachedReview);
    setCreditLimit(reviewCreditLimit(cachedReview) ?? 20);
    setLoadingLatest(true); setRunning(false); setStopRequested(false); setError(null); setIndex(0); setProgress(null); setBudgetUpdating(false);
    const request = ++requestRef.current;
    const key = cacheKey(projectId);
    void apiFetch(`/projects/${projectId}/m5/claims/latest`, { method: "POST" })
      .then((data: { review?: Review | null; progress?: ClaimProgress }) => {
        if (requestRef.current !== request || projectRef.current !== projectId || cacheKey(projectId) !== key) return;
        if (data?.review) {
          saveReview(data.review, projectId, key);
          // Latest includes a read-only persisted history, so reopened paused
          // and completed reviews remain informative without another request.
          if (data.progress) setProgress(data.progress);
        }
      })
      .catch((exc) => {
        if (requestRef.current === request && projectRef.current === projectId && cacheKey(projectId) === key) {
          setError(exc instanceof Error ? exc.message : "Không thể tải lần đánh giá gần nhất.");
        }
      })
      .finally(() => {
        if (requestRef.current === request && projectRef.current === projectId && cacheKey(projectId) === key) setLoadingLatest(false);
      });
    return () => { requestRef.current += 1; stopRef.current = true; };
  }, [projectId, saveReview]);

  useEffect(() => {
    if (!running || review?.status !== "running") return;
    const request = requestRef.current;
    const requestProject = projectId;
    const key = cacheKey(projectId);
    const reviewId = review.review_id;
    let disposed = false;
    let inFlight = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      if (disposed || inFlight) return;
      inFlight = true;
      try {
        const next = await apiFetch(`/projects/${requestProject}/m5/claims/${reviewId}/progress`, { method: "POST" }) as ClaimProgress;
        if (!disposed && requestRef.current === request && projectRef.current === requestProject && cacheKey(requestProject) === key) {
          setProgress(next);
          if (next.billing) setReview(current => current?.review_id === reviewId ? { ...current, billing: next.billing } : current);
        }
      } catch {
        // Progress is optional read-only context. The pending review request is
        // still authoritative, so a transient poll failure is not a review error.
      } finally {
        inFlight = false;
        if (!disposed) timer = setTimeout(poll, 1_000);
      }
    };
    timer = setTimeout(poll, 1_000);
    return () => { disposed = true; if (timer) clearTimeout(timer); };
  }, [projectId, review?.review_id, review?.status, running]);

  const runChunks = useCallback(async (initial: Review, request: number, requestProject: string, key: string) => {
    let current = initial;
    saveReview(current, requestProject, key);
    try {
      while (current.status === "running" && !stopRef.current) {
        const next = await apiFetch(`/projects/${requestProject}/m5/claims/${current.review_id}/next`, { method: "POST" }) as Review & { progress?: ClaimProgress };
        if (requestRef.current !== request || projectRef.current !== requestProject || cacheKey(requestProject) !== key) return;
        current = next;
        if (!current) throw new Error("Máy chủ không trả về tiến độ đánh giá.");
        if (next.progress) setProgress(next.progress);
        saveReview(current, requestProject, key);
      }
    } catch (exc) {
      if (requestRef.current === request && projectRef.current === requestProject && cacheKey(requestProject) === key) {
        // A budget rejection can arrive after its final model call was charged.
        // Refreshing the read-only progress once shows the actual balance and activity.
        try {
          const finalProgress = await apiFetch(`/projects/${requestProject}/m5/claims/${current.review_id}/progress`, { method: "POST" }) as ClaimProgress;
          if (requestRef.current === request && projectRef.current === requestProject && cacheKey(requestProject) === key) {
            setProgress(finalProgress);
            if (finalProgress.billing) setReview(active => active?.review_id === current.review_id ? { ...active, billing: finalProgress.billing } : active);
          }
        } catch {
          // The original failure remains the useful error if progress is unavailable.
        }
        if (exc instanceof ApiError && exc.status === 402 && exc.body?.error?.code === "claim_review_budget") {
          setError("Đã chạm ngưỡng credit. Cập nhật ngưỡng rồi tiếp tục đánh giá.");
        } else {
          setError(exc instanceof Error ? exc.message : "Không thể tiếp tục đánh giá nhận định.");
        }
      }
    }
  }, [projectId, saveReview]);

  const start = useCallback(async () => {
    if (operationRef.current || budgetUpdateRef.current) return;
    operationRef.current = true;
    const operation = ++operationVersionRef.current;
    const request = ++requestRef.current;
    const requestProject = projectId;
    const key = cacheKey(projectId);
    stopRef.current = false; setStopRequested(false); setRunning(true); setError(null); setProgress(null);
    try {
      // Nhận định is anchored to persisted bytes; never start from unsaved TipTap prose.
      await onFlush();
      if (requestRef.current !== request || projectRef.current !== requestProject || cacheKey(requestProject) !== key) return;
      const started = await apiFetch(`/projects/${requestProject}/m5/claims/start`, {
        method: "POST", body: { credit_limit: creditLimit },
      }) as Review;
      if (requestRef.current !== request || projectRef.current !== requestProject || cacheKey(requestProject) !== key) return;
      await runChunks(started, request, requestProject, key);
    } catch (exc) {
      if (requestRef.current === request && projectRef.current === requestProject && cacheKey(requestProject) === key) setError(exc instanceof Error ? exc.message : "Không thể bắt đầu đánh giá nhận định.");
    } finally {
      if (requestRef.current === request && projectRef.current === requestProject && cacheKey(requestProject) === key) setRunning(false);
      if (operationVersionRef.current === operation) operationRef.current = false;
    }
  }, [creditLimit, onFlush, projectId, runChunks]);

  const resume = useCallback(() => {
    if (!review || review.status !== "running" || operationRef.current || budgetUpdateRef.current) return;
    operationRef.current = true;
    const operation = ++operationVersionRef.current;
    const request = ++requestRef.current; const requestProject = projectId; const key = cacheKey(projectId);
    stopRef.current = false; setStopRequested(false); setRunning(true); setError(null);
    void runChunks(review, request, requestProject, key).finally(() => {
      if (requestRef.current === request && projectRef.current === requestProject && cacheKey(requestProject) === key) setRunning(false);
      if (operationVersionRef.current === operation) operationRef.current = false;
    });
  }, [projectId, review, runChunks]);
  const stop = () => { stopRef.current = true; setStopRequested(true); };
  const updateBudget = useCallback(async () => {
    if (!review || review.status !== "running" || running || budgetUpdateRef.current) return;
    budgetUpdateRef.current = true;
    const request = ++requestRef.current;
    const requestProject = projectId;
    const key = cacheKey(projectId);
    setBudgetUpdating(true); setError(null);
    try {
      const updated = await apiFetch(`/projects/${requestProject}/m5/claims/${review.review_id}/budget`, {
        method: "POST", body: { credit_limit: creditLimit },
      }) as Review;
      if (requestRef.current === request && projectRef.current === requestProject && cacheKey(requestProject) === key) {
        saveReview(updated, requestProject, key);
      }
    } catch (exc) {
      if (requestRef.current === request && projectRef.current === requestProject && cacheKey(requestProject) === key) {
        setError(exc instanceof Error ? exc.message : "Không thể cập nhật ngưỡng credit.");
      }
    } finally {
      if (requestRef.current === request) setBudgetUpdating(false);
      budgetUpdateRef.current = false;
    }
  }, [creditLimit, projectId, review, running, saveReview]);
  const suggestions = review?.suggestions ?? [];
  const suggestion = suggestions[Math.min(index, Math.max(suggestions.length - 1, 0))];

  const decide = async (item: Suggestion, action: "accept" | "reject") => {
    if (busyId || running || decisionRef.current) return;
    decisionRef.current = true;
    const request = ++requestRef.current;
    const requestProject = projectId;
    const key = cacheKey(projectId);
    const reviewId = review?.review_id;
    setBusyId(item.id); setError(null);
    try {
      // The server verifies this fingerprint too, but flushing first makes the
      // explicit stale response meaningful instead of racing the editor queue.
      await onFlush();
      if (requestRef.current !== request || projectRef.current !== requestProject || cacheKey(requestProject) !== key) return;
      const response: any = await apiFetch(
        `/projects/${requestProject}/m5/claims/${reviewId}/suggestions/${item.id}/${action}`,
        { method: "POST" },
      );
      if (requestRef.current !== request || projectRef.current !== requestProject || cacheKey(requestProject) !== key) return;
      const next = response?.review as Review | undefined;
      if (next) saveReview(next);
      if (action === "accept" && response?.chapter_name && typeof response?.chapter?.prose === "string") {
        onAccepted({ revision: `${item.id}:${Date.now()}`, chapterName: response.chapter_name,
          prose: response.chapter.prose, documentFingerprint: response.chapter.document_fingerprint });
      }
    } catch (exc) {
      if (requestRef.current === request && projectRef.current === requestProject && cacheKey(requestProject) === key) setError(exc instanceof Error ? exc.message : action === "accept" ? "Không thể chấp nhận đề xuất." : "Không thể bỏ đề xuất.");
    } finally { if (requestRef.current === request) setBusyId(null); decisionRef.current = false; }
  };

  return <div className="h-full overflow-y-auto bg-[#fbfbfa] p-3.5">
    <div className="rounded-2xl border border-ink-100 bg-white p-4">
      <button type="button" onClick={onBack} className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-[.1em] text-primary-600 hover:underline"><ArrowLeft className="h-3 w-3" /> Review</button>
      <h3 className="mt-2 text-[17px] font-semibold tracking-[-.02em] text-ink-900">Độ tin cậy của nhận định</h3>
      <p className="mt-2 text-[12px] leading-5 text-ink-600">Tìm nguồn học thuật và đối chiếu bằng chứng cho từng nhận định. Kết quả chỉ tạo đề xuất; không tự thay đổi luận văn.</p>
      {loadingLatest ? <p role="status" className="mt-3 text-xs text-ink-500"><Loader2 className="mr-1 inline h-3.5 w-3.5 animate-spin" />Đang tải lần đánh giá gần nhất…</p> : !review ? <>
        <CreditLimitInput value={creditLimit} onChange={setCreditLimit} />
        <p className="mb-0 mt-1 text-[10.5px] leading-4 text-ink-500">Ngưỡng dừng: {creditLimit} credit. Hệ thống dừng trước lượt mô hình tiếp theo khi đã chạm ngưỡng.</p>
        <button type="button" onClick={() => void start()} disabled={running} className="mt-3 inline-flex h-8 items-center gap-1.5 rounded-lg bg-primary-600 px-3 text-[11px] font-semibold text-white disabled:opacity-60"><Play className="h-3.5 w-3.5" />Bắt đầu đánh giá</button>
      </> : <>
        <Coverage review={review} running={running} />
        <BillingSummary billing={review.billing} />
        <ActivityHistory progress={progress} running={running} />
        <div className="mt-3 flex flex-wrap gap-2">
          {review.status === "running" && !running && <><CreditLimitInput value={creditLimit} onChange={setCreditLimit} disabled={budgetUpdating} className="mt-0" />
            <button type="button" onClick={() => void updateBudget()} disabled={budgetUpdating} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-ink-200 px-2.5 text-[11px] font-semibold text-ink-700 disabled:opacity-60">{budgetUpdating && <Loader2 className="h-3.5 w-3.5 animate-spin" />}Cập nhật ngưỡng</button></>}
          {review.status === "running" && !running && <button type="button" onClick={resume} disabled={budgetUpdating} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-primary-600 px-2.5 text-[11px] font-semibold text-white disabled:opacity-60"><Play className="h-3.5 w-3.5" />Tiếp tục</button>}
          {running && <button type="button" onClick={stop} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-ink-200 px-2.5 text-[11px] font-semibold text-ink-700"><Pause className="h-3.5 w-3.5" />Dừng sau đoạn này</button>}
          {!running && <button type="button" onClick={() => void start()} disabled={running || budgetUpdating} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-ink-200 px-2.5 text-[11px] font-semibold text-ink-700 disabled:opacity-60"><RotateCcw className="h-3.5 w-3.5" />Đánh giá lại</button>}
        </div>
        {stopRequested && running && <p className="mt-2 text-[10.5px] text-ink-500">Sẽ dừng sau đoạn đang xử lý. Bạn có thể tiếp tục sau.</p>}
      </>}
      {error && <p role="alert" className="mt-3 text-[11px] leading-5 text-red-700">{error}</p>}
    </div>
    {review?.warnings?.length ? <div className="mt-3 rounded-xl border border-amber-100 bg-amber-50 p-3 text-[11px] leading-5 text-amber-800"><AlertTriangle className="mr-1 inline h-3.5 w-3.5" />{review.warnings.map((warning, i) => <p key={i} className="m-0">{warning}</p>)}</div> : null}
    {suggestion && <SuggestionCard item={suggestion} position={index} total={suggestions.length} busy={busyId === suggestion.id || running}
      onPrevious={() => setIndex(i => Math.max(0, i - 1))} onNext={() => setIndex(i => Math.min(suggestions.length - 1, i + 1))}
      onJump={() => onSelectChapter?.(suggestion.chapter)} onAccept={() => void decide(suggestion, "accept")} onReject={() => void decide(suggestion, "reject")} />}
    {review && !suggestions.length && review.status === "completed" && <p className="mt-4 rounded-xl border border-ink-100 bg-white p-4 text-center text-[12px] text-ink-500">Không có đề xuất chỉnh sửa cho các nhận định đã đánh giá.</p>}
  </div>;
}

function CreditLimitInput({ value, onChange, disabled = false, className = "mt-3" }: {
  value: number; onChange: (value: number) => void; disabled?: boolean; className?: string;
}) {
  return <label className={`${className} block text-[11px] font-semibold text-ink-700`}>Giới hạn credit
    <input aria-label="Giới hạn credit" type="number" min={1} max={500} step={1} value={value} disabled={disabled}
      onChange={event => onChange(Math.min(500, Math.max(1, Math.trunc(event.currentTarget.valueAsNumber || 1))))}
      className="ml-2 h-8 w-20 rounded-lg border border-ink-200 bg-white px-2 text-[12px] text-ink-800 disabled:opacity-60" />
  </label>;
}

function BillingSummary({ billing }: { billing?: Billing }) {
  if (!billing) return null;
  const tokens = billing.prompt_tokens + billing.completion_tokens;
  return <div className="mt-3 rounded-xl border border-ink-100 bg-white p-3 text-[10.5px] leading-4 text-ink-600">
    <p className="m-0 font-semibold text-ink-700">Đã dùng {billing.credits_charged} / {billing.credits_limit} credit · {tokens} token</p>
    <p className="mb-0 mt-1">Ngưỡng dừng: {billing.credits_limit} credit. Khi chạm ngưỡng, hệ thống dừng trước lượt mô hình tiếp theo; lượt đang chạy có thể hoàn tất sau ngưỡng.</p>
    <p className="mb-0 mt-1">Kết quả tìm kiếm hoặc định danh từ bộ nhớ đệm không tạo lượt mô hình mới và không tính thêm credit.</p>
  </div>;
}

function Coverage({ review, running }: { review: Review; running: boolean }) {
  const coverage = review.coverage;
  const pct = coverage.chars_total ? Math.min(100, Math.round(coverage.chars_processed / coverage.chars_total * 100)) : 0;
  return <div className="mt-4 rounded-xl bg-ink-50 p-3"><div className="flex justify-between text-[11px] text-ink-700"><span>{review.status === "completed" ? "Đã đánh giá" : running ? "Đang đánh giá" : "Đã tạm dừng"} {review.chunks_completed}/{review.chunks_total} đoạn</span><span>{pct}% văn bản</span></div><div className="mt-2 h-1.5 overflow-hidden rounded bg-ink-200"><div className="h-full bg-primary-600 transition-all" style={{ width: `${pct}%` }} /></div><p className="mb-0 mt-2 text-[10.5px] leading-4 text-ink-500">{coverage.claims_assessed}/{coverage.claims_total} nhận định đã đối chiếu · {coverage.claims_unresolved} chưa giải quyết · {review.sources_verified_unique} nguồn đã xác minh riêng biệt</p></div>;
}

const activityLabels: Record<string, string> = {
  queued: "Đã xếp hàng cho đoạn tiếp theo",
  analyzing: "Đang nhận diện nhận định",
  claims_identified: "Đã nhận diện nhận định",
  searching: "Đang tìm nguồn học thuật",
  search_queued: "Đã xếp truy vấn tìm nguồn",
  parallel_searching: "Đang tra cứu song song",
  parallel_verifying: "Đang xác minh song song",
  verifying: "Đang xác minh thư mục nguồn",
  search_results: "Đã nhận kết quả tìm kiếm",
  evaluating: "Đang đối chiếu bằng chứng",
  chunk_done: "Đã hoàn tất đoạn",
  budget_paused: "Đã dừng theo ngưỡng credit",
  error: "Đoạn này chưa hoàn tất",
};

function activityText(activity: ClaimProgress["activities"][number]) {
  switch (activity.stage) {
    case "analyzing": return `Đang phân tích đoạn ${activity.count ?? ""}`.trim();
    case "claims_identified": return `Đã nhận diện ${activity.count ?? 0} nhận định`;
    case "search_results": return `Đã tìm được ${activity.count ?? 0} nguồn`;
    case "parallel_searching": return `Đang tra cứu song song ${activity.count ?? 0} truy vấn`;
    case "parallel_verifying": return `Đang xác minh song song ${activity.count ?? 0} nguồn`;
    case "verifying": return `Đang xác minh nguồn ${activity.count ?? ""}`.trim();
    case "evaluating": return `Đang đối chiếu ${activity.count ?? 0} nguồn`;
    case "chunk_done": return `Đã hoàn tất đoạn ${activity.count ?? ""}`.trim();
    default: return activityLabels[activity.stage] ?? activity.stage;
  }
}

function ActivityHistory({ progress, running }: { progress: ClaimProgress | null; running: boolean }) {
  if (!progress || !Array.isArray(progress.activities) || !progress.activities.length) return null;
  return <div aria-live="polite" className="mt-3 rounded-xl border border-ink-100 bg-white p-3">
    <p className="m-0 text-[10px] font-bold uppercase tracking-[.08em] text-ink-500">Hoạt động tìm nguồn</p>
    <ol className="mb-0 mt-2 max-h-[180px] space-y-1.5 overflow-y-auto pl-4 text-[10.5px] leading-4 text-ink-600">
      {[...progress.activities].reverse().map((activity, index) => <li key={`${activity.at ?? index}:${activity.stage}`} className="pl-0.5">
        {running && index === 0 && <Loader2 aria-label="Đang xử lý" className="mr-1 inline h-3 w-3 animate-spin text-primary-600" />}
        <span>{activityText(activity)}</span>
        {activity.query && <span className="text-ink-500"> · “{activity.query}”</span>}
      </li>)}
    </ol>
  </div>;
}

function SuggestionCard({ item, position, total, busy, onPrevious, onNext, onJump, onAccept, onReject }: { item: Suggestion; position: number; total: number; busy: boolean; onPrevious: () => void; onNext: () => void; onJump: () => void; onAccept: () => void; onReject: () => void }) {
  const sourceUrl = safeUrl(item.source?.url) ?? (item.source?.doi ? `https://doi.org/${item.source.doi.replace(/^https?:\/\/doi\.org\//i, "")}` : undefined);
  const evidenceUrl = safeUrl(item.evidence?.source_url);
  const acceptDisabled = busy || item.status !== "pending" || !item.actionable;
  const rejectDisabled = busy || item.status !== "pending";
  return <article className="mt-3 rounded-2xl border border-ink-100 bg-white p-4"><div className="flex items-start justify-between gap-3"><div><span className="rounded bg-amber-50 px-1.5 py-0.5 text-[9px] font-bold uppercase text-amber-800">{labels[item.classification] ?? item.classification}</span><p className="mb-0 mt-2 text-[10.5px] font-semibold text-ink-400">{chapterLabels[item.chapter] ?? item.chapter} · {position + 1}/{total}</p></div><div className="flex gap-1"><button type="button" aria-label="Đề xuất trước" disabled={position === 0} onClick={onPrevious} className="rounded p-1 text-ink-500 disabled:opacity-30"><ChevronLeft className="h-4 w-4" /></button><button type="button" aria-label="Đề xuất tiếp" disabled={position >= total - 1} onClick={onNext} className="rounded p-1 text-ink-500 disabled:opacity-30"><ChevronRight className="h-4 w-4" /></button></div></div><p className="mt-3 text-[11.5px] leading-5 text-ink-700">{item.rationale_vi}</p><Diff oldText={item.anchor.old_text} proposedText={item.proposed_text} />
    {item.source && <div className="mt-3 rounded-xl bg-ink-50 p-3 text-[11px]"><p className="m-0 font-semibold text-ink-800">{item.source.title}</p><p className="mb-0 mt-1 text-ink-500">{(item.source.authors ?? []).join(", ")}{item.source.year ? ` (${item.source.year})` : ""}{item.source.venue ? ` · ${item.source.venue}` : ""}</p><p className="mb-0 mt-1 text-[10px] text-ink-500">{item.source.verified ? "Đã xác minh thư mục" : "Chưa xác minh thư mục"}{item.source.provider ? ` · ${item.source.provider}` : ""}</p>{sourceUrl && <a href={sourceUrl} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-[10px] font-semibold text-primary-700 hover:underline">Mở nguồn <ExternalLink className="h-3 w-3" /></a>}</div>}
    {item.evidence && <blockquote className="mt-3 border-l-2 border-primary-200 pl-3 text-[11px] leading-5 text-ink-600"><p className="m-0 text-[10px] font-semibold text-primary-700">{item.evidence.kind === "full_text" ? "Đoạn toàn văn" : "Tóm tắt"} · {evidenceLabels[item.evidence.relation]}</p><p className="mb-0 mt-1">{item.evidence.text}</p>{evidenceUrl && <a href={evidenceUrl} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-[10px] font-semibold text-primary-700 hover:underline">Xem bằng chứng <ExternalLink className="h-3 w-3" /></a>}</blockquote>}
    <div className="mt-4 flex flex-wrap gap-2"><button type="button" onClick={onJump} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-ink-200 px-2.5 text-[10.5px] font-semibold text-ink-700"><FileSearch className="h-3.5 w-3.5" />Đi tới chương</button><button type="button" disabled={acceptDisabled} onClick={onAccept} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-primary-600 px-2.5 text-[10.5px] font-semibold text-white disabled:opacity-50">{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}Chấp nhận</button><button type="button" disabled={rejectDisabled} onClick={onReject} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-ink-200 px-2.5 text-[10.5px] font-semibold text-ink-700 disabled:opacity-50"><X className="h-3.5 w-3.5" />Bỏ qua</button>{item.status !== "pending" && <span className="self-center text-[10.5px] text-ink-500">{item.status === "accepted" ? "Đã chấp nhận" : item.status === "rejected" ? "Đã bỏ qua" : "Đề xuất đã cũ"}</span>}</div></article>;
}
function Diff({ oldText, proposedText }: { oldText: string; proposedText: string | null }) { return <div className="mt-3 space-y-2 text-[11px] leading-5"><div className="rounded-lg bg-red-50 p-2.5 text-red-900"><span className="block text-[9px] font-bold uppercase text-red-700">Hiện tại</span>{oldText}</div>{proposedText && <div className="rounded-lg bg-emerald-50 p-2.5 text-emerald-900"><span className="block text-[9px] font-bold uppercase text-emerald-700">Đề xuất</span>{proposedText}</div>}</div>; }
