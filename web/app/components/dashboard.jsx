"use client";

import Link from "next/link";
import { useMe } from "../lib/use-me";

export const Dashboard = ({ papers = [], loading = false, error = null }) => {
  const me = useMe();
  const username = me.data?.username || me.data?.email?.split("@")[0] || "there";

  return (
    <section className="space-y-8 max-w-6xl mx-auto w-full">
      {/* Header: greeting + CTA on the left, credit card on the right */}
      <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-6">
        <div className="flex-1 space-y-6">
          <div>
            <h1 className="text-2xl font-bold text-ink-900">Hi, {username}</h1>
            <p className="text-ink-500 mt-1">
              {loading
                ? "Loading your drafts…"
                : papers.length === 0
                ? "No drafts yet — start your first one."
                : "Pick up where you left off, or start a new draft."}
            </p>
          </div>

          <Link
            href="/chat"
            className="w-full max-w-md flex items-center justify-center gap-3 py-3 px-5 bg-primary-600 text-white font-semibold rounded-xl hover:bg-primary-700 transition-all focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 shadow-sm"
          >
            <div className="w-5 h-5 bg-white/20 rounded-full flex items-center justify-center">
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
            </div>
            <span>Start New Draft</span>
          </Link>
        </div>

        {/* Credit Balance card */}
        <div className="bg-white rounded-xl p-5 shadow-sm border border-ink-100 min-w-[320px]">
          <div className="flex items-start justify-between mb-3">
            <div>
              <p className="text-xs text-ink-500 mb-0.5">Credit Balance</p>
              <p className="text-xl font-bold text-ink-900">
                {(me.data?.credit || 0).toLocaleString()}
              </p>
            </div>
            <div className="w-7 h-7 bg-primary-50 rounded-full flex items-center justify-center">
              <svg className="w-3.5 h-3.5 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
          </div>
          <div className="space-y-2 pt-3 border-t border-ink-100">
            <div className="flex items-center justify-between">
              <p className="text-xs text-ink-500">Email</p>
              <p className="text-xs font-medium text-ink-900 truncate ml-2">{me.data?.email || "—"}</p>
            </div>
            <div className="flex items-center justify-between">
              <p className="text-xs text-ink-500">User ID</p>
              <p className="text-xs font-medium text-ink-900 font-mono">{me.data?.id?.slice(0, 8) || "—"}</p>
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error.message || "Could not load papers"}
        </div>
      )}

      {!loading && papers.length === 0 && !error && (
        <div className="bg-white rounded-xl border border-dashed border-ink-200 p-12 text-center">
          <h2 className="text-base font-semibold text-ink-900">Start your first thesis</h2>
          <p className="text-sm text-ink-500 mt-2 max-w-md mx-auto">
            Pick a topic, choose your settings, and the agents will draft a fully cited paper in minutes.
          </p>
        </div>
      )}

      {/* Papers table */}
      {papers.length > 0 && (
        <div className="bg-white rounded-xl p-4 sm:p-6 space-y-4 shadow-sm border border-ink-100">
          <h2 className="text-lg sm:text-xl font-semibold text-ink-900">Your Drafts</h2>

          <div className="overflow-x-auto">
            <table className="min-w-full hidden md:table">
              <thead>
                <tr className="border-b border-ink-200">
                  <th className="py-3 pr-3 text-left text-sm font-medium text-primary-600 w-16">No</th>
                  <th className="py-3 text-left text-sm font-medium text-primary-600">Draft Title</th>
                  <th className="py-3 text-left text-sm font-medium text-ink-500 w-32">Level</th>
                  <th className="py-3 text-left text-sm font-medium text-ink-500 w-28">Status</th>
                  <th className="py-3 text-left text-sm font-medium text-ink-500 w-32">Date Created</th>
                  <th className="py-3 pl-6 w-28"></th>
                </tr>
              </thead>
              <tbody>
                {papers.map((p, idx) => (
                  <PaperRow key={p.id} p={p} index={idx + 1} />
                ))}
              </tbody>
            </table>

            {/* Mobile cards */}
            <div className="md:hidden divide-y divide-ink-100">
              {papers.map((p, idx) => (
                <PaperMobileRow key={p.id} p={p} index={idx + 1} />
              ))}
            </div>
          </div>
        </div>
      )}
    </section>
  );
};

function PaperRow({ p, index }) {
  const tab = p.status === "done" ? "editor" : "run";
  return (
    <tr className="border-b border-ink-100 hover:bg-ink-50/50 transition-colors">
      <td className="py-5 pr-3 whitespace-nowrap text-sm text-ink-500">
        {index.toString().padStart(2, "0")}.
      </td>
      <td className="py-5">
        <span className="text-sm text-ink-900 block truncate max-w-[300px] lg:max-w-[400px]">
          {p.title || "Untitled"}
        </span>
      </td>
      <td className="py-5 text-sm text-ink-500">{p.level || "—"}</td>
      <td className="py-5"><StatusBadge status={p.status} /></td>
      <td className="py-5 whitespace-nowrap text-left text-sm text-ink-500">
        {p.updated_at ? new Date(p.updated_at).toLocaleDateString("en-GB") : "—"}
      </td>
      <td className="py-5 pl-6 whitespace-nowrap text-left">
        <Link
          href={`/paper/${p.id}?tab=${tab}`}
          className="inline-flex items-center px-4 py-1.5 border border-primary-600 text-primary-600 text-sm font-medium rounded-full hover:bg-primary-50 transition-colors"
        >
          View Detail
        </Link>
      </td>
    </tr>
  );
}

function PaperMobileRow({ p, index }) {
  const tab = p.status === "done" ? "editor" : "run";
  return (
    <div className="py-3">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm text-ink-400 shrink-0">{index.toString().padStart(2, "0")}.</span>
            <span className="text-sm font-medium text-ink-900 truncate">{p.title || "Untitled"}</span>
          </div>
          <div className="mt-1 ml-7 flex items-center gap-2">
            <StatusBadge status={p.status} />
            <span className="text-xs text-ink-400">
              {p.updated_at ? new Date(p.updated_at).toLocaleDateString("en-GB") : "—"}
            </span>
          </div>
        </div>
        <Link
          href={`/paper/${p.id}?tab=${tab}`}
          className="inline-flex items-center px-3 py-1 border border-primary-600 text-primary-600 text-xs font-medium rounded-full hover:bg-primary-50 transition-colors shrink-0"
        >
          View
        </Link>
      </div>
    </div>
  );
}

function StatusBadge({ status }) {
  const map = {
    running: "bg-primary-50 text-primary-600",
    done: "bg-green-50 text-green-700",
    failed: "bg-red-50 text-red-700",
    canceled: "bg-ink-100 text-ink-500",
    draft: "bg-ink-100 text-ink-500",
  };
  const cls = map[status] || "bg-ink-100 text-ink-500";
  const label = status === "running" ? "Generating" : status === "done" ? "Complete" : status || "—";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium capitalize ${cls}`}>
      {label}
    </span>
  );
}
