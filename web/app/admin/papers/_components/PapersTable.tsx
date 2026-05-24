"use client";

import { useState } from "react";
import useSWR from "swr";

import { AdminTable, type AdminColumn } from "@/app/components/admin/AdminTable";
import { swrFetcher } from "@/app/lib/api";

type Row = {
  id: string; owner_email: string; owner_id: string;
  topic: string; academic_level: string; model_tier: string;
  status: string; created_at: string | null;
};

type ListResp = { items: Row[]; total: number; page: number; page_size: number };

const STATUSES = ["", "draft", "running", "done", "failed", "canceled"];

export default function PapersTable() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const params = new URLSearchParams({ page: String(page), page_size: "20" });
  if (status) params.set("status", status);
  const { data, isLoading } = useSWR<ListResp>(`/admin/papers?${params.toString()}`, swrFetcher);

  const columns: AdminColumn<Row>[] = [
    { key: "topic", header: "Topic", render: (r) => <span className="font-medium truncate block max-w-md">{r.topic}</span> },
    { key: "owner", header: "Owner", render: (r) => r.owner_email },
    { key: "level", header: "Level", render: (r) => r.academic_level },
    { key: "tier", header: "Tier", render: (r) => r.model_tier },
    { key: "status", header: "Status", render: (r) => <StatusPill status={r.status} /> },
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
        <h1 className="text-2xl font-bold text-ink-900">Papers</h1>
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

function StatusPill({ status }: { status: string }) {
  const map: Record<string, string> = {
    done: "bg-green-50 text-green-700",
    running: "bg-blue-50 text-blue-700",
    failed: "bg-red-50 text-red-700",
    canceled: "bg-ink-100 text-ink-700",
    draft: "bg-ink-50 text-ink-500",
  };
  const cls = map[status] || "bg-ink-100 text-ink-700";
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${cls}`}>{status}</span>;
}
