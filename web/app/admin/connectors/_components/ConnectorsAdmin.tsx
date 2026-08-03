"use client";

import { useState } from "react";
import useSWR from "swr";

import { AdminTable, type AdminColumn } from "@/app/components/admin/AdminTable";
import { apiFetch, swrFetcher } from "@/app/lib/api";

/**
 * MCP connector usage.
 *
 * The MCP server's own access log says "POST /mcp 200" and nothing else — same
 * line for every user and every tool — so this page is the only way to answer
 * who used the connector, how much, and whether it worked.
 *
 * It shows SIZES, never the prose. mcp_tool_calls deliberately doesn't store
 * the text: an audit trail that quietly accumulates everyone's thesis drafts is
 * a liability, and sizes answer the operational questions without it.
 */

type Call = {
  id: string;
  user_email: string;
  user_id: string;
  client_id: string | null;
  tool: string;
  ok: boolean;
  error: string | null;
  duration_ms: number;
  input_chars: number;
  output_chars: number;
  created_at: string;
};

type CallsResp = { items: Call[]; total: number; page: number; page_size: number };

type Summary = {
  users: {
    user_id: string; user_email: string; calls: number; failed: number;
    input_chars: number; calls_24h: number; last_call: string | null;
  }[];
  grants: { user_email: string; client_name: string; connected_at: string }[];
  totals: { calls: number; users_with_calls: number; live_grants: number };
};

const PAGE_SIZE = 25;

function when(iso: string) {
  return new Date(iso).toLocaleString();
}

function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="rounded-2xl border border-ink-100 bg-white px-4 py-3 shadow-sm">
      <div className="text-[11.5px] font-semibold uppercase tracking-wide text-ink-500">{label}</div>
      <div className="mt-0.5 text-2xl font-bold tabular-nums text-ink-900">{value}</div>
      {hint && <div className="mt-0.5 text-[12px] text-ink-500">{hint}</div>}
    </div>
  );
}

export default function ConnectorsAdmin() {
  const [page, setPage] = useState(1);
  // "Failures only" is the default reason to open this page, so it's one click
  // rather than a filter buried in a dropdown.
  const [failedOnly, setFailedOnly] = useState(false);
  const [userId, setUserId] = useState<string | null>(null);

  const body: Record<string, unknown> = { page, page_size: PAGE_SIZE };
  if (failedOnly) body.ok = false;
  if (userId) body.user_id = userId;

  // apiFetch, not swrFetcher: swrFetcher POSTs with no body, so the filters
  // would be silently dropped. Per CLAUDE.md the filters belong in the JSON
  // body rather than a query string.
  const { data: calls, isLoading } = useSWR<CallsResp>(
    ["/admin/connectors/calls", JSON.stringify(body)],
    () => apiFetch("/admin/connectors/calls", { method: "POST", body }) as Promise<CallsResp>,
  );
  const { data: summary } = useSWR<Summary>("/admin/connectors/summary", swrFetcher);

  const columns: AdminColumn<Call>[] = [
    { key: "when", header: "When", render: (r) => when(r.created_at), className: "whitespace-nowrap" },
    { key: "user", header: "User", render: (r) => r.user_email },
    { key: "tool", header: "Tool", render: (r) => r.tool },
    {
      key: "ok",
      header: "Result",
      render: (r) =>
        r.ok ? (
          <span className="text-green-700">ok</span>
        ) : (
          // The error key is the point of the row — "no_anchor" tells you the
          // student was asked for a writing sample, not that anything broke.
          <span className="text-red-700">{r.error || "failed"}</span>
        ),
    },
    { key: "in", header: "In", render: (r) => `${r.input_chars.toLocaleString()} ch`, className: "tabular-nums" },
    { key: "out", header: "Out", render: (r) => `${r.output_chars.toLocaleString()} ch`, className: "tabular-nums" },
    { key: "dur", header: "Took", render: (r) => `${(r.duration_ms / 1000).toFixed(1)}s`, className: "tabular-nums" },
  ];

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="m-0 text-[22px] font-extrabold tracking-tight text-ink-900">
          MCP connectors
        </h1>
        <p className="mt-1 text-[13px] text-ink-500">
          Who connected Claude/ChatGPT to DoThesis, and what they called. Sizes
          only — the passages themselves are never stored.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Live grants" value={summary?.totals.live_grants ?? "—"} hint="accounts connected" />
        <Stat label="Total calls" value={summary?.totals.calls ?? "—"} />
        <Stat label="Users who called" value={summary?.totals.users_with_calls ?? "—"} />
        <Stat
          label="Connected, never used"
          // The giveaway's drop-off number: granted access but never invoked a
          // tool. Computed here because it's a difference between two lists the
          // API returns separately.
          value={
            summary
              ? Math.max(
                  0,
                  new Set(summary.grants.map((g) => g.user_email)).size -
                    summary.users.filter((u) => u.calls > 0).length,
                )
              : "—"
          }
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => { setFailedOnly((v) => !v); setPage(1); }}
          className={`rounded-lg border px-3 py-1.5 text-[12.5px] font-semibold ${
            failedOnly
              ? "border-red-300 bg-red-50 text-red-700"
              : "border-ink-200 text-ink-600 hover:bg-ink-50"
          }`}
        >
          Failures only
        </button>
        {userId && (
          <button
            type="button"
            onClick={() => { setUserId(null); setPage(1); }}
            className="rounded-lg border border-ink-200 px-3 py-1.5 text-[12.5px] font-semibold text-ink-600 hover:bg-ink-50"
          >
            Clear user filter ✕
          </button>
        )}
      </div>

      <AdminTable
        columns={columns}
        rows={calls?.items ?? []}
        total={calls?.total ?? 0}
        page={page}
        pageSize={PAGE_SIZE}
        onPageChange={setPage}
        onRowClick={(r) => { setUserId(r.user_id); setPage(1); }}
        isLoading={isLoading}
        emptyMessage={
          failedOnly ? "No failed calls." : "No connector calls recorded yet."
        }
      />

      {summary && summary.users.length > 0 && (
        <div className="rounded-2xl border border-ink-100 bg-white p-4 shadow-sm">
          <div className="text-[13px] font-bold text-ink-900">Per user</div>
          <table className="mt-2 min-w-full text-[13px]">
            <thead>
              <tr className="text-left text-[11.5px] uppercase tracking-wide text-ink-500">
                <th className="py-1.5 pr-4">User</th>
                <th className="py-1.5 pr-4 text-right">Calls</th>
                <th className="py-1.5 pr-4 text-right">24h</th>
                <th className="py-1.5 pr-4 text-right">Failed</th>
                <th className="py-1.5 pr-4 text-right">Text in</th>
                <th className="py-1.5">Last call</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100">
              {summary.users.map((u) => (
                <tr
                  key={u.user_id}
                  onClick={() => { setUserId(u.user_id); setPage(1); }}
                  className="cursor-pointer hover:bg-ink-50"
                >
                  <td className="py-1.5 pr-4">{u.user_email}</td>
                  <td className="py-1.5 pr-4 text-right tabular-nums">{u.calls}</td>
                  <td className="py-1.5 pr-4 text-right tabular-nums">{u.calls_24h}</td>
                  <td className="py-1.5 pr-4 text-right tabular-nums">
                    {u.failed > 0 ? <span className="text-red-700">{u.failed}</span> : "—"}
                  </td>
                  <td className="py-1.5 pr-4 text-right tabular-nums">
                    {u.input_chars.toLocaleString()}
                  </td>
                  <td className="py-1.5">{u.last_call ? when(u.last_call) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
