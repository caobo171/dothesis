"use client";

import { useState } from "react";
import useSWR, { mutate } from "swr";

import { AdminTable, type AdminColumn } from "@/app/components/admin/AdminTable";
import { apiFetch, swrFetcher } from "@/app/lib/api";

type Row = {
  id: string; paper_id: string; paper_topic: string;
  owner_email: string; status: string; phase: string | null;
  progress: number;
  started_at: string | null; finished_at: string | null;
  error_text: string | null;
};

type ListResp = { items: Row[]; total: number; page: number; page_size: number };

const STATUSES = ["", "queued", "running", "done", "failed", "canceled"];

export default function JobsTable() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("running");
  const [cancelling, setCancelling] = useState<string | null>(null);
  const params = new URLSearchParams({ page: String(page), page_size: "20" });
  if (status) params.set("status", status);
  const key = `/admin/jobs?${params.toString()}`;
  const { data, isLoading } = useSWR<ListResp>(key, swrFetcher);

  async function doCancel(jobId: string) {
    setCancelling(jobId);
    try {
      await apiFetch(`/admin/jobs/${jobId}/cancel`, { method: "POST" });
      mutate(key);
    } finally {
      setCancelling(null);
    }
  }

  const columns: AdminColumn<Row>[] = [
    { key: "topic", header: "Topic", render: (r) => <span className="font-medium truncate block max-w-md">{r.paper_topic}</span> },
    { key: "owner", header: "Owner", render: (r) => r.owner_email },
    { key: "status", header: "Status", render: (r) => r.status },
    { key: "phase", header: "Phase", render: (r) => r.phase || "—" },
    { key: "progress", header: "Progress", render: (r) => `${Math.round((r.progress || 0) * 100)}%`, className: "tabular-nums" },
    {
      key: "actions",
      header: "",
      render: (r) => r.status === "running" || r.status === "queued"
        ? (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); doCancel(r.id); }}
            disabled={cancelling === r.id}
            className="rounded-md border border-red-200 px-2 py-1 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
          >
            {cancelling === r.id ? "Cancelling…" : "Cancel"}
          </button>
        )
        : <span className="text-ink-400">—</span>,
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-2xl font-bold text-ink-900">Jobs</h1>
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
