"use client";

import {
  MessageSquare,
  Plus,
  Receipt,
  RotateCcw,
  Sparkles,
  Ticket,
  Wrench,
} from "lucide-react";
import Link from "next/link";
import useSWR from "swr";

import { swrFetcher } from "@/app/lib/api";
import { useLocale } from "@/app/lib/i18n/LocaleProvider";
import type { MessageKey } from "@/app/lib/i18n/messages/en";
import { useMe } from "@/app/lib/use-me";


// Resolved project + thread for a thread-scoped (chat_turn) row, so the
// Activity cell can deep-link back to the conversation that spent the credits.
// Null for grants/top-ups and any row whose thread was since deleted.
type TxnLink = {
  project_id: string;
  thread_id: string;
  project_name: string;
  thread_name: string;
} | null;

type Txn = {
  id: number;
  delta: number;
  reason: string;
  ref_type: string | null;
  ref_id: string | null;
  created_at: string | null;
  link?: TxnLink;
};

// Label keys for the ledger `reason` codes written by credit_ledger. The tool
// entries were showing raw slugs ("verify-citations") to students, because the
// tools bill under their own name and this map predates them.
const REASON_KEY: Record<string, MessageKey> = {
  chat_turn: "txn.reason.chatTurn",
  auto_run: "txn.reason.autoRun",
  paper_run: "txn.reason.paperRun",
  purchase: "txn.reason.purchase",
  refund: "txn.reason.refund",
  "humanize": "txn.tool.humanize",
  "humanize-docx": "txn.tool.humanizeDocx",
  "cite-docx": "txn.tool.citeDocx",
  "verify-citation": "txn.tool.verifyCitation",
  "verify-citations": "txn.tool.verifyCitations",
  "writing-rhythm": "txn.tool.rhythm",
  "plagiarism-check": "txn.tool.plagiarism",
  "similarity-docx": "txn.tool.similarityDocx",
  "similarity-docx-corpus": "txn.tool.similarityDocxCorpus",
  "scan-similarity-docx": "txn.tool.scanSimilarityDocx",
};

function reasonIcon(reason: string) {
  if (reason === "purchase") return Plus;
  if (reason === "refund") return RotateCcw;
  if (reason === "chat_turn") return MessageSquare;
  if (reason === "auto_run" || reason === "paper_run") return Sparkles;
  return Wrench;
}

function localDayKey(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
}

function formatDayLabel(
  iso: string,
  locale: string,
  t: (key: MessageKey) => string,
): string {
  const d = new Date(iso);
  const now = new Date();
  const start = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diffDays = Math.round((start(now) - start(d)) / 86_400_000);
  if (diffDays === 0) return t("txn.today");
  if (diffDays === 1) return t("txn.yesterday");
  return d.toLocaleDateString(locale === "vi" ? "vi-VN" : "en-US", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function formatTime(iso: string, locale: string): string {
  return new Date(iso).toLocaleTimeString(locale === "vi" ? "vi-VN" : "en-US", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Project and thread often share a title; printing both is the same name twice. */
function contextLabel(link: TxnLink): string | null {
  if (!link) return null;
  const a = (link.project_name || "").trim();
  const b = (link.thread_name || "").trim();
  if (!a && !b) return null;
  if (!a) return b;
  if (!b) return a;
  if (a === b) return a;
  if (a.startsWith(b) || b.startsWith(a)) return a.length >= b.length ? a : b;
  return `${a} · ${b}`;
}

/** Ledger rows that must stay one-for-one (financial events). */
function isSingletonTxn(x: Txn): boolean {
  return x.reason === "purchase" || x.reason === "refund";
}

// Same activity within a day collapses to one row (e.g. seven chat turns on
// one project). Purchases/refunds stay separate; thread-scoped spends merge on
// project+thread; tool debits with no link merge on reason alone.
function mergeKey(x: Txn): string {
  if (isSingletonTxn(x)) return `singleton:${x.id}`;
  if (x.link) {
    return `link:${x.reason}:${x.link.project_id}:${x.link.thread_id}`;
  }
  if (x.ref_type && x.ref_id) {
    return `ref:${x.reason}:${x.ref_type}:${x.ref_id}`;
  }
  return `reason:${x.reason}`;
}

type TxnGroup = {
  key: string;
  reason: string;
  link: TxnLink;
  delta: number;
  count: number;
  first_at: string | null;
  last_at: string | null;
};

function groupSimilarInDay(txns: Txn[]): TxnGroup[] {
  const map = new Map<string, TxnGroup>();
  const order: string[] = [];

  for (const x of txns) {
    const key = mergeKey(x);
    const existing = map.get(key);
    if (existing) {
      existing.delta += x.delta;
      existing.count += 1;
      if (x.created_at) {
        if (!existing.first_at || x.created_at < existing.first_at) {
          existing.first_at = x.created_at;
        }
        if (!existing.last_at || x.created_at > existing.last_at) {
          existing.last_at = x.created_at;
        }
      }
      continue;
    }
    order.push(key);
    map.set(key, {
      key,
      reason: x.reason,
      link: x.link ?? null,
      delta: x.delta,
      count: 1,
      first_at: x.created_at,
      last_at: x.created_at,
    });
  }

  return order.map((k) => map.get(k)!);
}

function formatTimeRange(
  first: string | null,
  last: string | null,
  locale: string,
): string {
  if (!last) return first ? formatTime(first, locale) : "";
  if (!first || first === last) return formatTime(last, locale);
  const [a, b] = first < last ? [first, last] : [last, first];
  return `${formatTime(a, locale)} – ${formatTime(b, locale)}`;
}

function groupByDay(txns: Txn[]): { key: string; iso: string; rows: TxnGroup[] }[] {
  const groups: { key: string; iso: string; rows: Txn[] }[] = [];
  for (const x of txns) {
    const iso = x.created_at;
    const key = iso ? localDayKey(iso) : "unknown";
    const last = groups[groups.length - 1];
    if (last && last.key === key) last.rows.push(x);
    else groups.push({ key, iso: iso || "", rows: [x] });
  }
  return groups.map((g) => ({ ...g, rows: groupSimilarInDay(g.rows) }));
}

export default function Transactions() {
  const me = useMe();
  const { t, locale } = useLocale();
  const numberLocale = locale === "vi" ? "vi-VN" : "en-US";
  const txns = useSWR<Txn[]>("/credit/transactions", swrFetcher);
  const rows = txns.data ?? [];
  const groups = groupByDay(rows);

  return (
    <section className="px-2 sm:px-4 lg:px-6">
      <div className="max-w-5xl mx-auto">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4 border-b border-ink-100 py-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-ink-900">{t("txn.title")}</h1>
            <p className="mt-1 text-sm text-ink-500">{t("txn.subtitle")}</p>
          </div>
          <div className="flex items-center gap-2 rounded-full bg-primary-50 px-3 py-1.5">
            <Ticket className="h-4 w-4 text-primary-600" />
            <span className="text-sm font-semibold tabular-nums text-primary-600">
              {t("txn.balance", { count: (me.data?.credit ?? 0).toLocaleString(numberLocale) })}
            </span>
          </div>
        </div>

        {txns.isLoading ? (
          <div className="space-y-2">
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i} className="h-14 animate-pulse rounded-xl bg-ink-100" />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <div className="rounded-2xl border border-ink-100 bg-white px-6 py-12 text-center">
            <Receipt className="mx-auto h-8 w-8 text-ink-300" />
            <p className="mt-3 text-sm font-medium text-ink-800">{t("txn.empty")}</p>
            <p className="mt-1 text-sm text-ink-500">{t("txn.emptyHint")}</p>
          </div>
        ) : (
          <div className="space-y-6">
            {groups.map((g) => (
              <section key={g.key}>
                <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-400">
                  {g.iso ? formatDayLabel(g.iso, locale, t) : "—"}
                </h2>
                <div className="overflow-hidden rounded-2xl border border-ink-100 bg-white">
                  {g.rows.map((x, i) => {
                    const Icon = reasonIcon(x.reason);
                    const label = REASON_KEY[x.reason] ? t(REASON_KEY[x.reason]) : x.reason;
                    const ctx = contextLabel(x.link);
                    const inner = (
                      <>
                        <span className="min-w-[6.5rem] shrink-0 whitespace-nowrap text-xs tabular-nums text-ink-400">
                          {formatTimeRange(x.first_at, x.last_at, locale)}
                        </span>
                        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-ink-50 text-ink-600">
                          <Icon className="h-4 w-4" />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium text-ink-900">
                            {label}
                            {x.count > 1 ? (
                              <span className="ml-1.5 text-xs font-normal text-ink-400">
                                {t("txn.group.count", { count: x.count.toLocaleString(numberLocale) })}
                              </span>
                            ) : null}
                          </span>
                          {ctx ? (
                            <span className="mt-0.5 block truncate text-xs text-ink-500">{ctx}</span>
                          ) : null}
                        </span>
                        <span
                          className={`shrink-0 text-sm font-semibold tabular-nums ${
                            x.delta < 0 ? "text-red-600" : "text-emerald-600"
                          }`}
                        >
                          {x.delta > 0 ? "+" : ""}
                          {x.delta.toLocaleString(numberLocale)}
                        </span>
                      </>
                    );
                    const rowClass =
                      "flex items-center gap-3 px-4 py-3 " +
                      (i > 0 ? "border-t border-ink-50 " : "") +
                      (x.link ? "hover:bg-ink-50/70" : "");
                    return x.link ? (
                      <Link
                        key={x.key}
                        href={`/chat/projects/${x.link.project_id}/threads/${x.link.thread_id}`}
                        className={rowClass + " no-underline"}
                      >
                        {inner}
                      </Link>
                    ) : (
                      <div key={x.key} className={rowClass}>
                        {inner}
                      </div>
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
        )}

        {/* The tool history moved to its own page (/tool-runs). It is a
            different list — a run that charged nothing writes no credit
            transaction at all — and it grew its own controls (download,
            re-run, delete, live progress) that do not belong inside a ledger.
            The pointer stays, because this is where a student comes when they
            ask where their credits went. */}
        <p className="mt-6 text-[13px] text-ink-500">
          {t("txn.tools.seeRuns")}{" "}
          <Link href="/tool-runs" className="font-semibold text-primary-700 hover:underline">
            {t("nav.toolUsage")}
          </Link>
        </p>
      </div>
    </section>
  );
}
