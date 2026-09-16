"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle, ArrowRight, BookCheck, Bot, Check, CheckCircle2, ChevronDown, CircleHelp, FileCheck2,
  Loader2, MessageSquareText, Play, RotateCcw, ScanSearch, ShieldCheck,
  Sparkles, SpellCheck2, MapPin,
} from "lucide-react";

import { apiFetch } from "@/app/lib/api";
import { tokenStore } from "@/app/lib/tokenStore";
import type { ChapterName } from "./OutlineRail";

type Finding = {
  issue: string; fix: string; chapter: string; severity: "hard" | "soft";
  question?: string | null;
  evidence?: { sentence?: string | null; expected?: unknown };
};
type Dimension = { name: string; score: number; weight: number; findings: Finding[] };
type ReviewResult = {
  overall: number;
  method: string;
  dimensions: Dimension[];
  blocking: string[];
  reviewed_at: string;
  review_id: string;
  review_kind: ReviewKind;
};
type ReviewKind = "claim_confidence" | "peer_review" | "source_quality" | "tone_of_voice" | "proofread";

// EditorSidePanel conditionally unmounts this component when its tab closes.
// Keep a very small browser-memory cache so a student can return to results in
// this session, but never persist review findings to disk or the server.
const REVIEW_SESSION_LIMIT = 8;
const reviewSessionCache = new Map<string, Partial<Record<ReviewKind, ReviewResult>>>();

function cacheKey(projectId: string) {
  // A project id alone can repeat after a logout/login in a long-lived tab.
  // Scope ephemeral output to the active bearer token without persisting it.
  return `${tokenStore.get() ?? "anonymous"}:${projectId}`;
}

function cacheResults(key: string, results: Partial<Record<ReviewKind, ReviewResult>>) {
  reviewSessionCache.delete(key);
  reviewSessionCache.set(key, results);
  while (reviewSessionCache.size > REVIEW_SESSION_LIMIT) {
    const oldest = reviewSessionCache.keys().next().value;
    if (oldest === undefined) break;
    reviewSessionCache.delete(oldest);
  }
}

const ACTIONS: Array<{ kind: ReviewKind; title: string; description: string; icon: React.ReactNode }> = [
  { kind: "claim_confidence", title: "Độ tin cậy nhận định", description: "Tìm nguồn và đối chiếu bằng chứng cho từng nhận định trước khi tạo đề xuất.", icon: <ScanSearch className="h-4 w-4" /> },
  { kind: "peer_review", title: "Peer review", description: "Chạy rubric trên bản luận văn đã lưu để nêu các điểm cần xem lại.", icon: <BookCheck className="h-4 w-4" /> },
  { kind: "source_quality", title: "Source quality", description: "Kiểm tra metadata và DOI khi có thể; không xác nhận phản biện khoa học hay rút bài.", icon: <FileCheck2 className="h-4 w-4" /> },
  { kind: "tone_of_voice", title: "Tone of voice", description: "Đánh giá tính học thuật, khách quan, rõ ràng và nhất quán.", icon: <MessageSquareText className="h-4 w-4" /> },
  { kind: "proofread", title: "Proofread", description: "Tìm lỗi ngữ pháp, chính tả, dấu câu và cách diễn đạt vụng.", icon: <SpellCheck2 className="h-4 w-4" /> },
];

const LABELS: Record<string, string> = {
  structure: "Cấu trúc", citations: "Trích dẫn", no_stubs: "Nội dung hoàn chỉnh",
  results_validity: "Báo cáo kết quả", methodology: "Phương pháp", writing: "Học thuật",
  advisor: "Ý kiến giảng viên", preflight: "Thiết kế nghiên cứu",
  instrument_quality: "Công cụ đo lường", stats_validity: "Tính đúng thống kê",
  source_verification: "Chất lượng nguồn", coherence: "Nhất quán", similarity: "Tương đồng",
};

const CHAPTER_MAP: Record<string, ChapterName> = {
  intro: "intro", introduction: "intro", lit_review: "lit_review",
  literature: "lit_review", methodology: "methodology", results: "results",
  conclusion: "conclusion",
};

export function ReviewPanel({ projectId, onSelectChapter, onAskAgent, onClaimConfidence }: {
  projectId: string;
  onSelectChapter?: (chapter: ChapterName) => void;
  onAskAgent?: (prompt: string) => void;
  onClaimConfidence?: () => void;
}) {
  // In-session only. Review output is a snapshot, not durable project state.
  const [results, setResults] = useState<Partial<Record<ReviewKind, ReviewResult>>>(() => reviewSessionCache.get(cacheKey(projectId)) ?? {});
  const [viewing, setViewing] = useState<ReviewKind | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runningKind, setRunningKind] = useState<ReviewKind | null>(null);
  const projectRef = useRef(projectId);
  const requestVersion = useRef(0);

  useEffect(() => {
    projectRef.current = projectId;
    requestVersion.current += 1;
    setResults(reviewSessionCache.get(cacheKey(projectId)) ?? {});
    setViewing(null); setError(null); setRunning(false); setRunningKind(null);
    // Invalidate a request after an unmount too; an old response must never
    // set state or seed another project with findings from this one.
    return () => { requestVersion.current += 1; };
  }, [projectId]);

  const run = async (kind: ReviewKind) => {
    const request = ++requestVersion.current;
    const requestProjectId = projectId;
    const requestCacheKey = cacheKey(projectId);
    setRunning(true);
    setRunningKind(kind);
    setError(null);
    try {
      const next = await apiFetch(`/projects/${projectId}/m5/review`, { method: "POST", body: { kind } });
      if (projectRef.current !== requestProjectId || requestVersion.current !== request || cacheKey(requestProjectId) !== requestCacheKey) return;
      setResults(current => {
        const updated = { ...current, [kind]: next as ReviewResult };
        cacheResults(requestCacheKey, updated);
        return updated;
      });
      setViewing(kind);
    } catch (exc) {
      if (projectRef.current !== requestProjectId || requestVersion.current !== request || cacheKey(requestProjectId) !== requestCacheKey) return;
      setError(exc instanceof Error ? exc.message : "Không thể chạy review lúc này.");
    } finally {
      if (projectRef.current === requestProjectId && requestVersion.current === request && cacheKey(requestProjectId) === requestCacheKey) {
        setRunning(false);
        setRunningKind(null);
      }
    }
  };

  const result = viewing ? results[viewing] : null;
  if (!result) {
    return (
      <div className="flex h-full flex-col overflow-y-auto bg-[#fbfbfa] p-4">
        <div className="mb-3 px-1">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary-50 text-primary-700">
            <Sparkles className="h-4 w-4" />
          </span>
          <h3 className="mt-3 text-[17px] font-semibold tracking-[-0.02em] text-ink-900">Review luận văn</h3>
          <p className="mt-2 text-[12.5px] leading-5 text-ink-500">
            Chọn loại kiểm tra phù hợp. Mỗi action đọc bản luận văn hiện tại và dùng validator riêng.
          </p>
        </div>
        <div className="space-y-2.5">
          {ACTIONS.map(action => {
            const isClaimConfidence = action.kind === "claim_confidence" && onClaimConfidence;
            const isRunning = running && runningKind === action.kind;
            const completed = results[action.kind];
            return (
              <div key={action.kind} className="rounded-2xl border border-ink-100 bg-white p-3.5">
                <div className="flex items-start gap-3">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-primary-50 text-primary-700">{action.icon}</span>
                  <div className="min-w-0 flex-1">
                    <h4 className="m-0 text-[13px] font-semibold text-ink-900">{action.title}</h4>
                    <p className="mb-0 mt-1 text-[11px] leading-[1.5] text-ink-500">{action.description}</p>
                  </div>
                </div>
                {isClaimConfidence ? <button type="button" onClick={onClaimConfidence} className="mt-3 inline-flex h-8 items-center gap-1.5 rounded-lg bg-primary-600 px-2.5 text-[11.5px] font-semibold text-white transition hover:bg-primary-700"><ScanSearch className="h-3.5 w-3.5" />Đánh giá nhận định</button> : completed ? <>
                  <button type="button" onClick={() => setViewing(action.kind)} className="mt-3 inline-flex h-8 items-center gap-1.5 rounded-lg bg-primary-600 px-2.5 text-[11.5px] font-semibold text-white transition hover:bg-primary-700"><CheckCircle2 className="h-3.5 w-3.5" />View results</button>
                  <button type="button" onClick={() => void run(action.kind)} disabled={running} className="ml-2 inline-flex h-8 items-center gap-1.5 rounded-lg border border-ink-200 px-2.5 text-[11.5px] font-semibold text-ink-700 transition hover:border-ink-300 hover:bg-ink-50 disabled:cursor-wait disabled:opacity-60"><RotateCcw className="h-3.5 w-3.5" />Run again</button>
                </> : <button type="button" onClick={() => void run(action.kind)} disabled={running}
                  className="mt-3 inline-flex h-8 items-center gap-1.5 rounded-lg border border-ink-200 px-2.5 text-[11.5px] font-semibold text-ink-700 transition hover:border-ink-300 hover:bg-ink-50 disabled:cursor-wait disabled:opacity-60">
                  {isRunning ? <><Loader2 className="h-3.5 w-3.5 animate-spin" />Đang chạy</> : <><Play className="h-3.5 w-3.5" />Run review</>}
                </button>}
              </div>
            );
          })}
        </div>
        {error && <p className="mt-3 text-xs leading-5 text-red-600">{error}</p>}
        {running && <div role="status" className="mt-4 rounded-2xl border border-ink-100 bg-white p-4 text-[11.5px] text-ink-600"><Loader2 className="mr-2 inline h-3.5 w-3.5 animate-spin" />Đang chạy review. Kết quả sẽ đánh giá bản luận văn đã lưu gần nhất.</div>}
      </div>
    );
  }

  return <ReviewResults result={result} running={running} error={error} onRun={() => run(result.review_kind)} onBack={() => setViewing(null)} onSelectChapter={onSelectChapter} onAskAgent={onAskAgent} />;
}

function ReviewResults({ result, running, error, onRun, onBack, onSelectChapter, onAskAgent }: {
  result: ReviewResult;
  running: boolean;
  error: string | null;
  onRun: () => Promise<void>;
  onBack: () => void;
  onSelectChapter?: (chapter: ChapterName) => void;
  onAskAgent?: (prompt: string) => void;
}) {
  const [resolved, setResolved] = useState<Set<string>>(new Set());
  useEffect(() => { setResolved(new Set()); }, [result.review_id]);
  const findings = useMemo(() => result.dimensions.flatMap(dimension =>
    (dimension.findings ?? []).map(finding => ({ ...finding, dimension: dimension.name }))), [result]);
  const strengths = result.dimensions.filter(dimension => dimension.score >= 0.85 && (dimension.findings?.length ?? 0) === 0);
  const overall = Math.round(result.overall * 10 * 10) / 10;
  const soundness = metric(result, ["results_validity", "stats_validity", "coherence"]);
  const presentation = metric(result, ["writing", "structure", "no_stubs"]);
  const contribution = metric(result, ["methodology", "citations", "source_verification"]);
  const action = ACTIONS.find(item => item.kind === result.review_kind) ?? ACTIONS[1];
  const isPeerReview = result.review_kind === "peer_review";
  const findingKey = (finding: Finding & { dimension: string }, index: number) => `${finding.dimension}-${index}-${finding.issue}`;
  const unresolved = findings.filter((finding, index) => !resolved.has(findingKey(finding, index)));
  // Only show questions that ask for specific missing evidence. Rephrasing
  // every finding as “how will you fix this?” duplicated the same error list.
  const questions = findings.filter(finding => finding.question).slice(0, 8);

  const jump = (chapter: string) => {
    const key = chapter.toLowerCase().trim();
    const mapped = CHAPTER_MAP[key] ?? Object.entries(CHAPTER_MAP).find(([needle]) => key.includes(needle))?.[1];
    if (mapped) onSelectChapter?.(mapped);
  };

  const askAgent = (finding: Finding & { dimension: string }) => {
    const citationInstruction = finding.dimension === "citations"
      ? "Xác minh citation bằng research tools. Nếu nguồn có thật, thêm hoặc sửa metadata trong M2 literature_sources qua commit_slice rồi cập nhật citation trong chương; nếu không xác minh được, loại citation hoặc thay bằng nguồn phù hợp đã xác minh. Không được bịa nguồn."
      : "Đọc state liên quan, sửa nguyên nhân gốc và cập nhật đúng slice qua commit_slice. Không bịa số liệu hoặc kết quả.";
    onAskAgent?.(
      `Hãy xử lý finding từ ${action.title} trong editor.\n\nVấn đề: ${finding.issue}\nĐề xuất của reviewer: ${finding.fix}\nChương: ${finding.chapter || "chưa xác định"}\n\n${citationInstruction}\nSau khi sửa, mô tả ngắn những gì đã thay đổi và vì sao.`
    );
  };

  return (
    <div className="h-full overflow-y-auto bg-[#fbfbfa] p-3.5">
      <div className="rounded-2xl border border-ink-100 bg-white p-4">
        <div className="flex items-start justify-between gap-3">
          <div><button type="button" onClick={onBack} className="m-0 text-[10px] font-bold uppercase tracking-[0.1em] text-primary-600 hover:underline">← Tất cả review</button>
            <h3 className="mb-0 mt-1 text-base font-semibold text-ink-900">{action.title}</h3></div>
          <div className="text-right"><span className="text-3xl font-semibold tracking-[-0.04em] text-ink-900 tabular-nums">{overall}</span><span className="text-xs text-ink-400">/10</span></div>
        </div>
        {isPeerReview && <div className="mt-4 grid grid-cols-3 gap-2">
          <Metric label="Độ vững" value={soundness} />
          <Metric label="Trình bày" value={presentation} />
          <Metric label="Đóng góp" value={contribution} />
        </div>}
        <p className="mt-4 text-[12px] leading-5 text-ink-600">
          Phát hiện {findings.length} vấn đề, gồm {result.blocking.length} điểm có thể ảnh hưởng trực tiếp tới độ tin cậy của luận văn. Phương pháp được nhận diện: <strong>{result.method}</strong>.
        </p>
        <p className="mt-2 text-[10.5px] leading-4 text-ink-500">{result.review_kind === "claim_confidence" ? "Phạm vi: đối chiếu citation/reference và tính nhất quán số liệu; không xác nhận nguồn toàn văn có hỗ trợ từng nhận định." : result.review_kind === "source_quality" ? "Phạm vi: kiểm tra metadata và DOI khi có thể; không xác nhận phản biện khoa học hoặc tình trạng rút bài." : "Kết quả là ảnh chụp của bản luận văn đã lưu tại thời điểm chạy review."}</p>
        {error && <p role="alert" className="mt-2 text-[11px] text-red-700">Không thể chạy lại review: {error}. Kết quả trước đó vẫn được giữ.</p>}
        {findings.length > 0 && (
          <div className="mt-3 rounded-xl bg-ink-50 p-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="m-0 text-[11.5px] font-semibold text-ink-800">Kế hoạch xử lý</p>
                <p className="mb-0 mt-0.5 text-[10.5px] text-ink-500">{resolved.size}/{findings.length} mục được bạn đánh dấu đã xem · còn {unresolved.length}</p>
              </div>
              {unresolved[0] ? (
                <button type="button" onClick={() => jump(unresolved[0].chapter)} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-ink-900 px-2.5 text-[10.5px] font-semibold text-white transition hover:bg-ink-700 active:translate-y-px">
                  Mục tiếp theo <ArrowRight className="h-3.5 w-3.5" />
                </button>
              ) : (
                <button type="button" onClick={() => void onRun()} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-emerald-600 px-2.5 text-[10.5px] font-semibold text-white transition hover:bg-emerald-700 active:translate-y-px">
                  <RotateCcw className="h-3.5 w-3.5" /> Kiểm tra lại
                </button>
              )}
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-ink-200"><div className="h-full rounded-full bg-emerald-500 transition-all duration-300" style={{ width: `${findings.length ? resolved.size / findings.length * 100 : 100}%` }} /></div>
          </div>
        )}
        <button type="button" onClick={() => void onRun()} disabled={running}
          className="mt-2 inline-flex h-8 items-center gap-1.5 rounded-lg border border-ink-200 px-2.5 text-[11.5px] font-semibold text-ink-700 transition hover:bg-ink-50 disabled:opacity-60">
          {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />} Chạy lại
        </button>
      </div>

      <ReviewGroup title="Điểm yếu" count={findings.length} icon={<AlertTriangle className="h-4 w-4 text-amber-600" />} defaultOpen>
        {findings.length ? findings.map((finding, index) => {
          const key = findingKey(finding, index);
          const done = resolved.has(key);
          return (
          <article key={key} className={"border-t border-ink-100 px-3 py-3 first:border-t-0 transition " + (done ? "bg-emerald-50/50 opacity-70" : "hover:bg-ink-50/70")}>
            <span className="flex items-center gap-2">
              <span className={"rounded px-1.5 py-0.5 text-[9px] font-bold uppercase " + (finding.severity === "hard" ? "bg-red-50 text-red-700" : "bg-amber-50 text-amber-700")}>{finding.severity === "hard" ? "Cần sửa" : "Cần xem lại"}</span>
              <span className="text-[10px] font-semibold text-ink-400">{LABELS[finding.dimension] ?? finding.dimension}</span>
            </span>
            <span className="mt-1.5 block text-[11.5px] leading-[1.55] text-ink-800">{finding.issue}</span>
            {finding.evidence?.sentence && <blockquote className="ml-0 mt-2 border-l-2 border-ink-200 pl-2 text-[11px] leading-[1.55] text-ink-600"><span className="block font-semibold">Câu cần đối chiếu</span>{finding.evidence.sentence}</blockquote>}
            <span className="mt-1 block text-[11px] leading-[1.5] text-ink-500">Gợi ý: {finding.fix}</span>
            <div className="mt-3 flex flex-wrap gap-1.5">
              <button type="button" onClick={() => jump(finding.chapter)} className="inline-flex h-7 items-center gap-1 rounded-md border border-ink-200 bg-white px-2 text-[10px] font-semibold text-ink-700 transition hover:border-ink-300 hover:bg-ink-50 active:translate-y-px">
                <MapPin className="h-3 w-3" /> Đi tới chương
              </button>
              {onAskAgent && (
                <button type="button" onClick={() => askAgent(finding)} className="inline-flex h-7 items-center gap-1 rounded-md bg-primary-600 px-2 text-[10px] font-semibold text-white transition hover:bg-primary-700 active:translate-y-px">
                  <Bot className="h-3 w-3" /> {finding.dimension === "citations" ? "Tìm nguồn & sửa" : "Nhờ agent xử lý"}
                </button>
              )}
              <button type="button" onClick={() => setResolved(current => { const next = new Set(current); done ? next.delete(key) : next.add(key); return next; })} className={"inline-flex h-7 items-center gap-1 rounded-md px-2 text-[10px] font-semibold transition active:translate-y-px " + (done ? "bg-emerald-100 text-emerald-800 hover:bg-emerald-200" : "border border-ink-200 bg-white text-ink-600 hover:bg-ink-50")}>
                {done ? <CheckCircle2 className="h-3 w-3" /> : <Check className="h-3 w-3" />} {done ? "Đã đánh dấu đã xem" : "Đánh dấu đã xem"}
              </button>
            </div>
          </article>
        ); }) : <EmptyLine text="Không phát hiện điểm yếu đáng kể." />}
      </ReviewGroup>

      <ReviewGroup title="Điểm mạnh" count={strengths.length} icon={<ShieldCheck className="h-4 w-4 text-emerald-600" />}>
        {strengths.length ? strengths.map(dimension => <EmptyLine key={dimension.name} text={`${LABELS[dimension.name] ?? dimension.name}: đạt yêu cầu.`} />) : <EmptyLine text="Chạy thêm review sau khi xử lý các vấn đề để xác nhận điểm mạnh." />}
      </ReviewGroup>

      {questions.length > 0 && <ReviewGroup title="Cần làm rõ" count={questions.length} icon={<CircleHelp className="h-4 w-4 text-primary-600" />}>
        {questions.map((finding, index) => (
          <button key={index} type="button" onClick={() => jump(finding.chapter)} className="block w-full border-t border-ink-100 px-3 py-3 text-left text-[11.5px] leading-[1.55] text-ink-700 first:border-t-0 hover:bg-ink-50">
            {finding.question}
          </button>
        ))}
      </ReviewGroup>}
    </div>
  );
}

function metric(result: ReviewResult, names: string[]) {
  const dims = result.dimensions.filter(dimension => names.includes(dimension.name));
  return dims.length ? Math.round((dims.reduce((sum, dimension) => sum + dimension.score, 0) / dims.length) * 4 * 10) / 10 : 0;
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div className="rounded-xl bg-ink-50 px-2 py-2.5 text-center"><div className="text-[15px] font-semibold tabular-nums text-ink-900">{value}/4</div><div className="mt-0.5 text-[9.5px] text-ink-500">{label}</div></div>;
}

function ReviewGroup({ title, count, icon, defaultOpen = false, children }: { title: string; count: number; icon: React.ReactNode; defaultOpen?: boolean; children: React.ReactNode }) {
  return (
    <details open={defaultOpen} className="group mt-3 overflow-hidden rounded-2xl border border-ink-100 bg-white">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3.5 py-3 text-[12.5px] font-semibold text-ink-900 [&::-webkit-details-marker]:hidden">
        {icon}<span className="flex-1">{title}</span><span className="rounded-md bg-ink-100 px-1.5 py-0.5 text-[10px] tabular-nums text-ink-600">{count}</span><ChevronDown className="h-3.5 w-3.5 text-ink-400 transition group-open:rotate-180" />
      </summary>
      <div className="border-t border-ink-100">{children}</div>
    </details>
  );
}

function EmptyLine({ text }: { text: string }) {
  return <p className="m-0 border-t border-ink-100 px-3 py-3 text-[11.5px] leading-5 text-ink-600 first:border-t-0">{text}</p>;
}
