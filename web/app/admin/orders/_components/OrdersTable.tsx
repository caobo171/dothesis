"use client";

import { useState } from "react";
import useSWR from "swr";

import { AdminTable, type AdminColumn } from "@/app/components/admin/AdminTable";
import { swrFetcher } from "@/app/lib/api";

type Row = {
  id: string; owner_email: string; package_id: string;
  credits: number; amount_cents: number; currency: string;
  amount_vnd: number | null; provider: string;
  status: string;
  polar_checkout_id: string | null; polar_order_id: string | null;
  sepay_memo: string | null; external_txn_id: string | null;
  created_at: string | null; paid_at: string | null;
};

type ListResp = { items: Row[]; total: number; page: number; page_size: number };

const STATUSES = ["", "pending", "paid", "refunded", "failed"];

/** What the customer was actually charged.
 *
 * `amount_cents` is always the USD list price, whatever currency the order was
 * billed in; `currency` says which, and `amount_vnd` carries the dong figure
 * for SePay. Formatting amount_cents with a "$" and appending `currency`
 * rendered every SePay order as "$24.99 VND" — the wrong number and a unit
 * that contradicts itself.
 */
function formatAmount(r: Row): string {
  if (r.currency === "VND" && r.amount_vnd != null) {
    return `${r.amount_vnd.toLocaleString("vi-VN")} ₫`;
  }
  return `$${(r.amount_cents / 100).toFixed(2)}`;
}

/** Whatever identifies this order on the provider's side.
 *
 * For SePay that is the transfer memo, which is the one thing that lets you
 * match a row here against a line on the bank statement — the usual "money
 * left my account but no credits arrived" ticket is unresolvable without it.
 */
function providerRef(r: Row): string {
  if (r.provider === "sepay") return r.sepay_memo || r.external_txn_id || "—";
  return r.polar_order_id || r.polar_checkout_id || r.external_txn_id || "—";
}

export default function OrdersTable() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const params = new URLSearchParams({ page: String(page), page_size: "20" });
  if (status) params.set("status", status);
  const { data, isLoading } = useSWR<ListResp>(`/admin/orders?${params.toString()}`, swrFetcher);

  const columns: AdminColumn<Row>[] = [
    { key: "owner", header: "Owner", render: (r) => <span className="font-medium">{r.owner_email}</span> },
    { key: "package", header: "Package", render: (r) => r.package_id },
    { key: "credits", header: "Credits", render: (r) => r.credits.toLocaleString(), className: "tabular-nums" },
    { key: "amount", header: "Amount", render: formatAmount, className: "tabular-nums" },
    { key: "status", header: "Status", render: (r) => r.status },
    { key: "provider", header: "Provider", render: (r) => r.provider, className: "text-xs text-ink-500" },
    // Was "Polar ID" and only ever rendered Polar's ids, so SePay and PayPal
    // rows showed "—" and lost their only traceable reference.
    { key: "ref", header: "Ref", render: providerRef, className: "font-mono text-xs text-ink-500" },
    {
      key: "created",
      header: "Created",
      render: (r) => r.created_at ? new Date(r.created_at).toLocaleDateString() : "—",
      className: "text-ink-500 text-xs",
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-2xl font-bold text-ink-900">Orders</h1>
        <select
          value={status}
          onChange={(e) => { setStatus(e.target.value); setPage(1); }}
          className="rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm shadow-sm"
        >
          {STATUSES.map((s) => <option key={s} value={s}>{s || "All statuses"}</option>)}
        </select>
      </div>
      <AdminTable<Row>
        columns={columns}
        rows={data?.items || []}
        total={data?.total || 0}
        page={page}
        pageSize={20}
        onPageChange={setPage}
        isLoading={isLoading}
      />
    </div>
  );
}
