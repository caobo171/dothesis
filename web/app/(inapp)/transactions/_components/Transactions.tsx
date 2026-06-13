"use client";

import { Receipt, Ticket } from "lucide-react";
import useSWR from "swr";

import { swrFetcher } from "@/app/lib/api";
import { useMe } from "@/app/lib/use-me";

type Txn = {
  id: number;
  delta: number;
  reason: string;
  ref_type: string | null;
  ref_id: string | null;
  created_at: string | null;
};

// Human labels for the ledger `reason` codes written by credit_ledger.
const REASON_LABEL: Record<string, string> = {
  chat_turn: "Chat / writing run",
  paper_run: "Thesis run",
  purchase: "Top-up",
  refund: "Refund",
};

export default function Transactions() {
  const me = useMe();
  const txns = useSWR<Txn[]>("/credit/transactions", swrFetcher);

  return (
    <section className="px-2 sm:px-4 lg:px-6">
      <div className="max-w-5xl mx-auto">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-6 py-3 border-b border-ink-100">
          <div className="flex items-center gap-2">
            <Receipt className="w-5 h-5 text-ink-500" />
            <h1 className="text-base font-semibold text-ink-900">Transactions</h1>
          </div>
          <div className="flex items-center gap-2 bg-primary-50 rounded-full px-3 py-1.5">
            <Ticket className="w-4 h-4 text-primary-600" />
            <span className="text-sm font-semibold text-primary-600">
              {me.data?.credit?.toLocaleString() || 0} Credit
            </span>
          </div>
        </div>

        {txns.data && txns.data.length > 0 ? (
          <div className="overflow-x-auto rounded-xl border border-ink-100">
            <table className="w-full text-sm">
              <thead className="bg-ink-50 text-ink-500 text-xs uppercase tracking-wide">
                <tr>
                  <th className="text-left font-medium px-4 py-2">Date</th>
                  <th className="text-left font-medium px-4 py-2">Activity</th>
                  <th className="text-right font-medium px-4 py-2">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {txns.data.map((t) => (
                  <tr key={t.id} className="hover:bg-ink-50/50">
                    <td className="px-4 py-2 text-ink-500 whitespace-nowrap">
                      {t.created_at ? new Date(t.created_at).toLocaleString() : "—"}
                    </td>
                    <td className="px-4 py-2 text-ink-900">
                      {REASON_LABEL[t.reason] || t.reason}
                    </td>
                    <td
                      className={`px-4 py-2 text-right font-semibold tabular-nums ${
                        t.delta < 0 ? "text-red-600" : "text-green-600"
                      }`}
                    >
                      {t.delta > 0 ? "+" : ""}
                      {t.delta.toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-ink-500">
            {txns.isLoading ? "Loading…" : "No credit usage yet."}
          </p>
        )}
      </div>
    </section>
  );
}
