"use client";

import { useState } from "react";
import useSWR, { mutate as globalMutate } from "swr";

import { AdminTable, type AdminColumn } from "@/app/components/admin/AdminTable";
import { Drawer } from "@/app/components/admin/Drawer";
import { apiFetch, swrFetcher } from "@/app/lib/api";

type AdminUserRow = {
  id: string;
  email: string;
  username: string | null;
  credit: number;
  is_super_admin: boolean;
  created_at: string | null;
};

type ListResponse = {
  items: AdminUserRow[];
  total: number;
  page: number;
  page_size: number;
};

export default function UsersTable() {
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [active, setActive] = useState<AdminUserRow | null>(null);
  const [delta, setDelta] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const params = new URLSearchParams({ page: String(page), page_size: "20" });
  if (q.trim()) params.set("q", q.trim());
  const key = `/admin/users?${params.toString()}`;
  const { data, isLoading } = useSWR<ListResponse>(key, swrFetcher);

  async function grant() {
    if (!active) return;
    const n = parseInt(delta, 10);
    if (!n) { setErr("Enter a non-zero integer"); return; }
    setBusy(true);
    setErr(null);
    try {
      await apiFetch(`/admin/users/${active.id}/credit`, {
        method: "POST",
        body: { delta: n },
      });
      setDelta("");
      globalMutate(key);
      setActive(null);
    } catch (e: any) {
      setErr(e?.body?.detail?.error?.code === "insufficient"
        ? "Cannot debit beyond current balance."
        : e?.message || "Grant failed.");
    } finally {
      setBusy(false);
    }
  }

  const columns: AdminColumn<AdminUserRow>[] = [
    { key: "email", header: "Email", render: (r) => <span className="font-medium">{r.email}</span> },
    { key: "username", header: "Username", render: (r) => r.username || "—" },
    { key: "credit", header: "Credit", render: (r) => r.credit.toLocaleString(), className: "tabular-nums" },
    {
      key: "admin",
      header: "Admin",
      render: (r) => r.is_super_admin
        ? <span className="rounded-full bg-primary-50 px-2 py-0.5 text-xs font-semibold text-primary-600">Yes</span>
        : <span className="text-ink-400">—</span>,
    },
    {
      key: "created",
      header: "Joined",
      render: (r) => r.created_at ? new Date(r.created_at).toLocaleDateString() : "—",
      className: "text-ink-500 text-xs",
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-2xl font-bold text-ink-900">Users</h1>
        <input
          type="search"
          placeholder="Search email or username…"
          value={q}
          onChange={(e) => { setQ(e.target.value); setPage(1); }}
          className="w-72 rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm shadow-sm focus:border-primary-500 focus:outline-none"
        />
      </div>
      <AdminTable<AdminUserRow>
        columns={columns}
        rows={data?.items || []}
        total={data?.total || 0}
        page={page}
        pageSize={20}
        onPageChange={setPage}
        onRowClick={(r) => { setActive(r); setDelta(""); setErr(null); }}
        isLoading={isLoading}
      />
      <Drawer open={!!active} onClose={() => setActive(null)} title={active?.email}>
        {active && (
          <div className="space-y-4">
            <div className="rounded-xl bg-ink-50 p-3 text-sm">
              <div className="text-ink-500">Balance</div>
              <div className="text-2xl font-bold text-ink-900">{active.credit.toLocaleString()} credits</div>
            </div>
            <div>
              <label className="text-xs font-medium text-ink-500">Grant or debit (negative = debit)</label>
              <div className="mt-1 flex gap-2">
                <input
                  type="number"
                  value={delta}
                  onChange={(e) => setDelta(e.target.value)}
                  placeholder="e.g. 500 or -100"
                  className="flex-1 rounded-xl border border-ink-200 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={grant}
                  disabled={busy}
                  className="rounded-xl bg-primary-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 disabled:opacity-50"
                >
                  {busy ? "Applying…" : "Apply"}
                </button>
              </div>
              {err && <div className="mt-2 text-xs text-red-700">{err}</div>}
            </div>
            <div className="text-xs text-ink-500">
              Admin status is managed in code (SUPER_ADMIN_EMAILS constant); not editable here.
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
