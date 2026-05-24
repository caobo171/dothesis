"use client";

import { useState } from "react";
import useSWR from "swr";

import { AdminTable, type AdminColumn } from "@/app/components/admin/AdminTable";
import { swrFetcher } from "@/app/lib/api";

type Row = {
  id: string; owner_email: string; package_id: string;
  credits: number; amount_cents: number; currency: string;
  status: string;
  polar_checkout_id: string | null; polar_order_id: string | null;
  created_at: string | null; paid_at: string | null;
};

type ListResp = { items: Row[]; total: number; page: number; page_size: number };

const STATUSES = ["", "pending", "paid", "refunded", "failed"];

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
    { key: "amount", header: "Amount", render: (r) => `$${(r.amount_cents / 100).toFixed(2)} ${r.currency}`, className: "tabular-nums" },
    { key: "status", header: "Status", render: (r) => r.status },
    { key: "polar", header: "Polar ID", render: (r) => r.polar_order_id || r.polar_checkout_id || "—", className: "font-mono text-xs text-ink-500" },
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
