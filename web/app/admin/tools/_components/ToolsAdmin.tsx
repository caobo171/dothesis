"use client";

import { useState } from "react";
import useSWR from "swr";

import { AdminTable, type AdminColumn } from "@/app/components/admin/AdminTable";
import { apiFetch, swrFetcher } from "@/app/lib/api";

/**
 * Standalone tool usage.
 *
 * The tools are the one surface with no project, no job and no thread behind
 * them, so admin/jobs and admin/papers never showed them at all — a student
 * could cite fifty documents and leave no trace anywhere an admin looks.
 *
 * The number this page is built around is UNCOLLECTED: charging is capped at
 * the caller's balance, so a student at zero is under-billed rather than
 * refused a document they already waited a minute for. That is a deliberate
 * trade, and it is only defensible while somebody can see what it adds up to.
 */

type Run = {
  id: string;
  user_email: string;
  user_id: string;
  surface: string;
  tool: string;
  ok: boolean;
  error: string | null;
  units: number;
  credits_cost: number;
  credits_charged: number;
  prompt_tokens: number;
  completion_tokens: number;
  duration_ms: number;
  created_at: string;
};

type RunsResp = { items: Run[]; total: number; page: number; page_size: number };

type Summary = {
  tools: {
    tool: string; runs: number; failed: number; units: number;
    credits_cost: number; credits_charged: number; tokens: number;
    runs_24h: number; users: number; last_run: string | null;
  }[];
  users: {
    user_id: string; user_email: string; runs: number;
    credits_cost: number; credits_charged: number; runs_24h: number;
    last_run: string | null;
  }[];
  totals: {
    runs: number; runs_24h: number; credits_cost: number;
    credits_charged: number; credits_uncollected: number;
  };
};

type Pricing = {
  per_unit: Record<string, number>;
  flat: Record<string, number>;
  free: string[];
  note: string;
};

const PAGE_SIZE = 25;

const when = (iso: string) => new Date(iso).toLocaleString();
const n = (v: number) => v.toLocaleString();

function Stat({ label, value, hint, alert }: {
  label: string; value: string | number; hint?: string; alert?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-ink-100 bg-white px-4 py-3 shadow-sm">
      <div className="text-[11.5px] font-semibold uppercase tracking-wide text-ink-500">{label}</div>
      <div className={`mt-0.5 text-2xl font-bold tabular-nums ${alert ? "text-[#8E6B2A]" : "text-ink-900"}`}>
        {value}
      </div>
      {hint && <div className="mt-0.5 text-[12px] text-ink-500">{hint}</div>}
    </div>
  );
}

export default function ToolsAdmin() {
  const [page, setPage] = useState(1);
  const [failedOnly, setFailedOnly] = useState(false);
  const [unpaidOnly, setUnpaidOnly] = useState(false);
  const [userId, setUserId] = useState<string | null>(null);
  const [tool, setTool] = useState<string | null>(null);

  const body: Record<string, unknown> = { page, page_size: PAGE_SIZE };
  if (failedOnly) body.ok = false;
  if (unpaidOnly) body.unpaid_only = true;
  if (userId) body.user_id = userId;
  if (tool) body.tool = tool;

  // apiFetch, not swrFetcher: swrFetcher POSTs with no body, so every filter
  // would be silently dropped. Per CLAUDE.md the filters live in the JSON body.
  const { data: runs, isLoading } = useSWR<RunsResp>(
    ["/admin/tools/runs", JSON.stringify(body)],
    () => apiFetch("/admin/tools/runs", { method: "POST", body }) as Promise<RunsResp>,
  );
  const { data: summary } = useSWR<Summary>("/admin/tools/summary", swrFetcher);
  const { data: pricing } = useSWR<Pricing>("/admin/tools/pricing", swrFetcher);

  const columns: AdminColumn<Run>[] = [
    { key: "when", header: "When", render: (r) => when(r.created_at), className: "whitespace-nowrap" },
    { key: "user", header: "User", render: (r) => r.user_email },
    {
      key: "tool",
      header: "Tool",
      // The surface rides along with the tool name rather than taking a column
      // of its own: it's only ever interesting next to what was called, and
      // "web" is the overwhelming default not worth a column of repetition.
      render: (r) => (
        <span>
          {r.tool}
          {r.surface !== "web" && (
            <span className="ml-1.5 rounded bg-ink-100 px-1.5 py-0.5 text-[11px] font-semibold text-ink-600">
              {r.surface}
            </span>
          )}
        </span>
      ),
    },
    {
      key: "ok",
      header: "Result",
      render: (r) =>
        r.ok ? <span className="text-green-700">ok</span>
             : <span className="text-red-700">{r.error || "failed"}</span>,
    },
    { key: "units", header: "Units", render: (r) => (r.units ? n(r.units) : "—"), className: "tabular-nums" },
    {
      key: "tokens",
      header: "Tokens",
      render: (r) => {
        const t = r.prompt_tokens + r.completion_tokens;
        return t ? n(t) : "—";
      },
      className: "tabular-nums",
    },
    {
      key: "credits",
      header: "Credits",
      // Cost and charged shown together whenever they disagree. One number
      // would hide the giveaway this page exists to measure.
      render: (r) =>
        r.credits_charged === r.credits_cost
          ? (r.credits_cost ? n(r.credits_cost) : "free")
          : <span className="text-[#8E6B2A]">{n(r.credits_charged)} / {n(r.credits_cost)}</span>,
      className: "tabular-nums",
    },
    { key: "dur", header: "Took", render: (r) => `${(r.duration_ms / 1000).toFixed(1)}s`, className: "tabular-nums" },
  ];

  const chip = (on: boolean) =>
    `rounded-lg border px-3 py-1.5 text-[12.5px] font-semibold ${
      on ? "border-primary-300 bg-primary-50 text-primary-700"
         : "border-ink-200 text-ink-600 hover:bg-ink-50"}`;

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="m-0 text-[22px] font-extrabold tracking-tight text-ink-900">
          Tools
        </h1>
        <p className="mt-1 text-[13px] text-ink-500">
          Humanize, citations, rhythm — every run outside a project. Counts and
          costs only; the passages themselves are never stored.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Runs" value={summary ? n(summary.totals.runs) : "—"}
              hint={summary ? `${n(summary.totals.runs_24h)} in the last 24h` : undefined} />
        <Stat label="Credits charged" value={summary ? n(summary.totals.credits_charged) : "—"} />
        <Stat label="Uncollected" value={summary ? n(summary.totals.credits_uncollected) : "—"}
              hint="run, but the balance couldn't cover it"
              alert={!!summary && summary.totals.credits_uncollected > 0} />
        <Stat label="Tools in use" value={summary ? summary.tools.length : "—"} />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={chip(failedOnly)}
                onClick={() => { setFailedOnly((v) => !v); setPage(1); }}>
          Failures only
        </button>
        <button type="button" className={chip(unpaidOnly)}
                onClick={() => { setUnpaidOnly((v) => !v); setPage(1); }}>
          Under-billed only
        </button>
        {tool && (
          <button type="button" onClick={() => { setTool(null); setPage(1); }}
                  className="rounded-lg border border-ink-200 px-3 py-1.5 text-[12.5px] font-semibold text-ink-600 hover:bg-ink-50">
            {tool} ✕
          </button>
        )}
        {userId && (
          <button type="button" onClick={() => { setUserId(null); setPage(1); }}
                  className="rounded-lg border border-ink-200 px-3 py-1.5 text-[12.5px] font-semibold text-ink-600 hover:bg-ink-50">
            Clear user filter ✕
          </button>
        )}
      </div>

      <AdminTable
        columns={columns}
        rows={runs?.items ?? []}
        total={runs?.total ?? 0}
        page={page}
        pageSize={PAGE_SIZE}
        onPageChange={setPage}
        onRowClick={(r) => { setUserId(r.user_id); setPage(1); }}
        isLoading={isLoading}
        emptyMessage={
          failedOnly ? "No failed runs."
            : unpaidOnly ? "Everything has been paid for."
              : "No tool runs recorded yet."
        }
      />

      {summary && summary.tools.length > 0 && (
        <div className="rounded-2xl border border-ink-100 bg-white p-4 shadow-sm">
          <div className="text-[13px] font-bold text-ink-900">Per tool</div>
          <div className="overflow-x-auto">
            <table className="mt-2 min-w-full text-[13px]">
              <thead>
                <tr className="text-left text-[11.5px] uppercase tracking-wide text-ink-500">
                  <th className="py-1.5 pr-4">Tool</th>
                  <th className="py-1.5 pr-4 text-right">Runs</th>
                  <th className="py-1.5 pr-4 text-right">24h</th>
                  <th className="py-1.5 pr-4 text-right">Users</th>
                  <th className="py-1.5 pr-4 text-right">Failed</th>
                  <th className="py-1.5 pr-4 text-right">Units</th>
                  <th className="py-1.5 pr-4 text-right">Tokens</th>
                  <th className="py-1.5 pr-4 text-right">Charged</th>
                  <th className="py-1.5 pr-4 text-right">Uncollected</th>
                  <th className="py-1.5">Last run</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {summary.tools.map((t) => {
                  const gap = t.credits_cost - t.credits_charged;
                  return (
                    <tr key={t.tool}
                        onClick={() => { setTool(t.tool); setPage(1); }}
                        className="cursor-pointer hover:bg-ink-50">
                      <td className="py-1.5 pr-4 font-medium">{t.tool}</td>
                      <td className="py-1.5 pr-4 text-right tabular-nums">{n(t.runs)}</td>
                      <td className="py-1.5 pr-4 text-right tabular-nums">{n(t.runs_24h)}</td>
                      <td className="py-1.5 pr-4 text-right tabular-nums">{n(t.users)}</td>
                      <td className="py-1.5 pr-4 text-right tabular-nums">
                        {t.failed > 0 ? <span className="text-red-700">{n(t.failed)}</span> : "—"}
                      </td>
                      <td className="py-1.5 pr-4 text-right tabular-nums">{t.units ? n(t.units) : "—"}</td>
                      <td className="py-1.5 pr-4 text-right tabular-nums">{t.tokens ? n(t.tokens) : "—"}</td>
                      <td className="py-1.5 pr-4 text-right tabular-nums">{n(t.credits_charged)}</td>
                      <td className="py-1.5 pr-4 text-right tabular-nums">
                        {gap > 0 ? <span className="text-[#8E6B2A]">{n(gap)}</span> : "—"}
                      </td>
                      <td className="py-1.5 whitespace-nowrap">{t.last_run ? when(t.last_run) : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {summary && summary.users.length > 0 && (
        <div className="rounded-2xl border border-ink-100 bg-white p-4 shadow-sm">
          <div className="text-[13px] font-bold text-ink-900">Per user</div>
          <div className="overflow-x-auto">
            <table className="mt-2 min-w-full text-[13px]">
              <thead>
                <tr className="text-left text-[11.5px] uppercase tracking-wide text-ink-500">
                  <th className="py-1.5 pr-4">User</th>
                  <th className="py-1.5 pr-4 text-right">Runs</th>
                  <th className="py-1.5 pr-4 text-right">24h</th>
                  <th className="py-1.5 pr-4 text-right">Charged</th>
                  <th className="py-1.5 pr-4 text-right">Uncollected</th>
                  <th className="py-1.5">Last run</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {summary.users.map((u) => {
                  const gap = u.credits_cost - u.credits_charged;
                  return (
                    <tr key={u.user_id}
                        onClick={() => { setUserId(u.user_id); setPage(1); }}
                        className="cursor-pointer hover:bg-ink-50">
                      <td className="py-1.5 pr-4">{u.user_email}</td>
                      <td className="py-1.5 pr-4 text-right tabular-nums">{n(u.runs)}</td>
                      <td className="py-1.5 pr-4 text-right tabular-nums">{n(u.runs_24h)}</td>
                      <td className="py-1.5 pr-4 text-right tabular-nums">{n(u.credits_charged)}</td>
                      <td className="py-1.5 pr-4 text-right tabular-nums">
                        {gap > 0 ? <span className="text-[#8E6B2A]">{n(gap)}</span> : "—"}
                      </td>
                      <td className="py-1.5 whitespace-nowrap">{u.last_run ? when(u.last_run) : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {pricing && (
        <div className="rounded-2xl border border-ink-100 bg-white p-4 shadow-sm">
          <div className="text-[13px] font-bold text-ink-900">Current rates</div>
          {/* Surfaced because the rates were picked for shape, not costed. A
              price nobody can see from here is a price nobody revisits. */}
          <p className="mt-1 mb-2 text-[12px] text-ink-500">{pricing.note}</p>
          <ul className="m-0 list-none p-0 text-[12.5px] text-ink-700">
            {Object.entries(pricing.per_unit).map(([k, v]) => (
              <li key={k} className="py-0.5">
                <span className="font-medium">{k}</span> — {v} credit{v === 1 ? "" : "s"} per lookup
              </li>
            ))}
            {Object.entries(pricing.flat).map(([k, v]) => (
              <li key={k} className="py-0.5">
                <span className="font-medium">{k}</span> — {v} credit{v === 1 ? "" : "s"} per run
              </li>
            ))}
            <li className="py-0.5 text-ink-500">
              free: {pricing.free.join(", ")}
            </li>
          </ul>
          <p className="mt-2 mb-0 text-[12px] text-ink-500">
            Change these in <code>api/app/pricing.py</code> — every route reads
            that table, nothing hardcodes a price.
          </p>
        </div>
      )}
    </div>
  );
}
