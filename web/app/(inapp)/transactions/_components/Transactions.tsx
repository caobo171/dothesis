"use client";

import { Receipt, Ticket } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
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

const TABS = ["credits", "tools"] as const;
type Tab = (typeof TABS)[number];

export default function Transactions() {
  const me = useMe();
  const t = useT();
  const txns = useSWR<Txn[]>("/credit/transactions", swrFetcher);
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const tab: Tab = params.get("tab") === "tools" ? "tools" : "credits";

  // replace, not push: flipping a tab is not a navigation a student wants to
  // walk back through — the back button should leave the page, not cycle tabs.
  const setTab = (next: Tab) =>
    router.replace(next === "credits" ? pathname : `${pathname}?tab=tools`,
                   { scroll: false });

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

        {/* Two lists, not one, and now two TABS rather than one long scroll.
            They answer different questions — "where did my credits go" and
            "what did I run, and can I get the file back" — and the second grew
            its own controls (download, re-run, delete, live progress), which
            were buried under the whole ledger.

            The tab lives in the URL so a reload, a back button or a pasted link
            lands where the student was. */}
        <div className="mb-5 flex items-center gap-1 border-b border-ink-100">
          {TABS.map((id) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              aria-current={tab === id ? "page" : undefined}
              className={`-mb-px border-b-2 px-3 py-2 text-[13px] font-semibold transition-colors ${
                tab === id
                  ? "border-primary-600 text-primary-700"
                  : "border-transparent text-ink-500 hover:text-ink-800"
              }`}
            >
              {t(id === "credits" ? "txn.tab.credits" : "txn.tab.tools")}
            </button>
          ))}
        </div>

        {tab === "tools" ? (
          <ToolRuns />
        ) : txns.data && txns.data.length > 0 ? (
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
      </div>
    </section>
  );
}
