"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import useSWR from "swr";

import { AdminTable, type AdminColumn } from "@/app/components/admin/AdminTable";
import { swrFetcher } from "@/app/lib/api";
import { useT } from "@/app/lib/i18n/LocaleProvider";
import { useQueryString } from "@/app/lib/useQueryString";

import { PaperListFilters } from "./PaperListFilters";

// Mirrors admin_papers.list_papers, which now reads `projects` (the legacy
// `papers` table it used to read has been empty since the v3 pivot). Project
// has no academic_level/model_tier, so LEVEL/TIER became FIELD/MODULE.
type Row = {
  id: string; owner_email: string; owner_id: string;
  topic: string; field: string | null; module: string;
  status: string; created_at: string | null;
};

type ListResp = { items: Row[]; total: number; page: number; page_size: number };

export default function PapersTable() {
  const t = useT();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { createMultipleQueryString } = useQueryString();

  const page = Math.max(1, Number(searchParams.get("page") ?? 1));
  const params = new URLSearchParams({ page: String(page), page_size: "20" });
  for (const key of ["q", "owner", "module", "status"] as const) {
    const value = searchParams.get(key);
    if (value) params.set(key, value);
  }
  const key = `/admin/papers?${params.toString()}`;
  const { data, isLoading } = useSWR<ListResp>(key, swrFetcher);

  const onFilterChange = (filterKey: string, value: string) => {
    router.push(`${pathname}?${createMultipleQueryString({ [filterKey]: value, page: "1" })}`);
  };

  const onPageChange = (nextPage: number) => {
    router.push(`${pathname}?${createMultipleQueryString({ page: String(nextPage) })}`);
  };

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
      <div>
        <h1 className="text-2xl font-bold text-ink-900">{t("admin.papers.title")}</h1>
        <p className="mt-1 text-sm text-ink-500">{t("admin.papers.subtitle")}</p>
      </div>

      <PaperListFilters searchParams={searchParams} onFilterChange={onFilterChange} />

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
        onPageChange={onPageChange}
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
