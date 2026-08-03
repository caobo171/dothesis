"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";

import { AdminTable, type AdminColumn } from "@/app/components/admin/AdminTable";
import { swrFetcher } from "@/app/lib/api";

// Mirrors admin_papers.list_papers, which now reads `projects` (the legacy
// `papers` table it used to read has been empty since the v3 pivot). Project
// has no academic_level/model_tier, so LEVEL/TIER became FIELD/MODULE.
type Row = {
  id: string; owner_email: string; owner_id: string;
  topic: string; field: string | null; module: string;
  status: string; created_at: string | null;
};

type ListResp = { items: Row[]; total: number; page: number; page_size: number };

// Filtering by module, not status: every project in the database is 'draft'
// (running/done/failed/canceled are *job* statuses), so a status filter can
// only ever match everything or nothing. Module is the axis with variance.
const MODULES = ["", "M1", "M2", "M3", "M4", "M5"];

export default function PapersTable() {
  const router = useRouter();
  const [page, setPage] = useState(1);
  const [module, setModule] = useState("");
  const params = new URLSearchParams({ page: String(page), page_size: "20" });
  if (module) params.set("module", module);
  const { data, isLoading } = useSWR<ListResp>(`/admin/papers?${params.toString()}`, swrFetcher);

  const columns: AdminColumn<Row>[] = [
    { key: "topic", header: "Topic", render: (r) => <span className="font-medium truncate block max-w-md">{r.topic}</span> },
    { key: "owner", header: "Owner", render: (r) => r.owner_email },
    { key: "field", header: "Field", render: (r) => r.field || "—" },
    {
      key: "module",
      header: "Module",
      render: (r) => (
        <span className="font-serif font-bold text-primary-600">{r.module}</span>
      ),
    },
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
          value={module}
          onChange={(e) => { setModule(e.target.value); setPage(1); }}
          className="rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm shadow-sm"
        >
          {MODULES.map((m) => <option key={m} value={m}>{m || "All modules"}</option>)}
        </select>
      </div>
      {/* A project's detail view IS the chat workspace — there is no separate
          admin detail page, and building one would duplicate the context panel
          and transcript that already exist. Super admins can read any project
          (auth_admin.readable_project) but not write to it, so this opens the
          real thing read-only rather than a second, thinner copy of it.
          AdminTable only adds the pointer cursor + row hover when onRowClick
          is set, which is why these rows looked and behaved inert before. */}
      <AdminTable<Row>
        columns={columns}
        rows={data?.items || []}
        total={data?.total || 0}
        page={page}
        pageSize={20}
        onPageChange={setPage}
        onRowClick={(r) => router.push(`/chat/projects/${r.id}`)}
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
