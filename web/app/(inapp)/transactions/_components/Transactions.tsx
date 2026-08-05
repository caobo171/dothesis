"use client";

import { Receipt, Ticket } from "lucide-react";
import Link from "next/link";
import useSWR from "swr";

import { swrFetcher } from "@/app/lib/api";
import { useT } from "@/app/lib/i18n/LocaleProvider";
import type { MessageKey } from "@/app/lib/i18n/messages/en";
import { useMe } from "@/app/lib/use-me";

import ToolRuns from "./ToolRuns";

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
};

export default function Transactions() {
  const me = useMe();
  const t = useT();
  const txns = useSWR<Txn[]>("/credit/transactions", swrFetcher);

  return (
    <section className="px-2 sm:px-4 lg:px-6">
      <div className="max-w-5xl mx-auto">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-6 py-3 border-b border-ink-100">
          <div className="flex items-center gap-2">
            <Receipt className="w-5 h-5 text-ink-500" />
            <h1 className="text-base font-semibold text-ink-900">{t("txn.title")}</h1>
          </div>
          <div className="flex items-center gap-2 bg-primary-50 rounded-full px-3 py-1.5">
            <Ticket className="w-4 h-4 text-primary-600" />
            <span className="text-sm font-semibold text-primary-600">
              {t("txn.balance", { count: me.data?.credit || 0 })}
            </span>
          </div>
        </div>

        {txns.data && txns.data.length > 0 ? (
          <div className="overflow-x-auto rounded-xl border border-ink-100">
            <table className="w-full text-sm">
              <thead className="bg-ink-50 text-ink-500 text-xs uppercase tracking-wide">
                <tr>
                  <th className="text-left font-medium px-4 py-2">{t("txn.col.date")}</th>
                  <th className="text-left font-medium px-4 py-2">{t("txn.col.activity")}</th>
                  <th className="text-right font-medium px-4 py-2">{t("txn.col.amount")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {txns.data.map((x) => (
                  <tr key={x.id} className="hover:bg-ink-50/50">
                    <td className="px-4 py-2 text-ink-500 whitespace-nowrap">
                      {x.created_at ? new Date(x.created_at).toLocaleString() : "—"}
                    </td>
                    <td className="px-4 py-2 text-ink-900">
                      {x.link ? (
                        <Link
                          href={`/chat/projects/${x.link.project_id}/threads/${x.link.thread_id}`}
                          className="group inline-flex flex-wrap items-baseline gap-x-1.5 text-primary-600 hover:underline"
                        >
                          <span>{REASON_KEY[x.reason] ? t(REASON_KEY[x.reason]) : x.reason}</span>
                          <span className="text-xs text-ink-400 group-hover:text-ink-500">
                            {x.link.project_name} · {x.link.thread_name}
                          </span>
                        </Link>
                      ) : (
                        REASON_KEY[x.reason] ? t(REASON_KEY[x.reason]) : x.reason
                      )}
                    </td>
                    <td
                      className={`px-4 py-2 text-right font-semibold tabular-nums ${
                        x.delta < 0 ? "text-red-600" : "text-green-600"
                      }`}
                    >
                      {x.delta > 0 ? "+" : ""}
                      {x.delta.toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-ink-500">
            {txns.isLoading ? t("txn.loading") : t("txn.empty")}
          </p>
        )}

        {/* Not merged into the table above: a run that charged nothing writes
            no credit transaction, so the two lists genuinely differ. */}
        <ToolRuns />
      </div>
    </section>
  );
}
