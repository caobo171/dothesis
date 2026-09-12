"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";

import { Select } from "@/app/components/ui/select";
import { apiFetch } from "@/app/lib/api";
import { useT } from "@/app/lib/i18n/LocaleProvider";

import { STATUS, STATUS_LABEL, type ListResp, type PostRow } from "./types";

/**
 * The post bank, all statuses.
 *
 * The public /blog route only ever shows what a reader may see, and the CLI
 * reports counts — so until this screen existed, "what is actually in the
 * bank, and what is it waiting on" had no answer you could click. That matters
 * most for the scheduled tranche: hundreds of posts that are real, paid for,
 * and invisible until their date.
 */

const PAGE_SIZE = 25;

function statusTone(status: number): string {
  if (status === STATUS.PUBLISHED) return "bg-[#EAF3EC] text-[#3A5740]";
  if (status === STATUS.SCHEDULED) return "bg-[#FBF3E3] text-[#8E6B2A]";
  return "bg-ink-100 text-ink-600";
}

function when(row: PostRow): string {
  const iso = row.status === STATUS.SCHEDULED ? row.scheduled_at : row.published_at;
  return iso ? new Date(iso).toLocaleDateString() : "—";
}

export default function BlogAdmin() {
  const t = useT();
  const [page, setPage] = useState(1);
  const [locale, setLocale] = useState("");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [pending, setPending] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const body = {
    page,
    page_size: PAGE_SIZE,
    locale: locale || null,
    status: status === "" ? null : Number(status),
    q: q || null,
  };
  const { data, isLoading, mutate } = useSWR<ListResp>(
    ["/admin/blog/list", page, locale, status, q],
    () => apiFetch("/admin/blog/list", { method: "POST", body }) as Promise<ListResp>,
  );

  async function remove(row: PostRow) {
    // A published post is a live URL with whatever traffic it has earned, so
    // the confirm names the post rather than asking a generic "are you sure".
    if (!window.confirm(`Delete “${row.title}”? This cannot be undone.`)) return;
    setBusy(row.id);
    setError(null);
    try {
      await apiFetch("/admin/blog/delete", { method: "POST", body: { id: row.id } });
      void mutate();
    } catch (e) {
      setError((e as Error)?.message || "Delete failed");
    } finally {
      setBusy(null);
    }
  }

  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const search = (value: string) => { setQ(value); setPage(1); };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-ink-900">
          Blog posts
          {data && <span className="ml-2 text-sm font-normal text-ink-500">{data.total}</span>}
        </h1>
        <div className="flex items-center gap-2">
          <Link href="/admin/blog/categories"
                className="rounded-xl border border-ink-200 px-3 py-2 text-sm font-semibold text-ink-700 hover:bg-ink-50">
            Categories
          </Link>
          <Link href="/admin/blog/create"
                className="rounded-xl bg-primary-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary-700">
            New post
          </Link>
        </div>
      </div>

      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => { e.preventDefault(); search(pending); }}
      >
        <input
          className="w-64 rounded-lg border border-ink-200 px-3 py-2 text-sm"
          placeholder="Title, slug or focus keyword"
          value={pending}
          onChange={(e) => setPending(e.target.value)}
        />
        <Select
          value={locale}
          onValueChange={(v) => { setLocale(v); setPage(1); }}
          options={[
            { value: "", label: t("admin.blog.allLocales") },
            { value: "vi", label: "vi" },
            { value: "en", label: "en" },
          ]}
          className="w-36"
        />
        <Select
          value={status}
          onValueChange={(v) => { setStatus(v); setPage(1); }}
          options={[
            { value: "", label: t("admin.blog.allStatuses") },
            { value: String(STATUS.DRAFT), label: t("admin.blog.draft") },
            { value: String(STATUS.PUBLISHED), label: t("admin.blog.published") },
            { value: String(STATUS.SCHEDULED), label: t("admin.blog.scheduled") },
          ]}
          className="w-40"
        />
        <button type="submit"
                className="rounded-lg border border-ink-200 px-3 py-2 text-sm font-semibold text-ink-700 hover:bg-ink-50">
          {t("admin.blog.search")}
        </button>
        {(q || locale || status) && (
          <button type="button"
                  onClick={() => { setPending(""); setQ(""); setLocale(""); setStatus(""); setPage(1); }}
                  className="text-sm text-ink-500 hover:text-ink-800">
            Clear
          </button>
        )}
      </form>

      {error && (
        <p className="rounded-lg border border-[#E6C9C9] bg-[#FBF0F0] px-3 py-2 text-[13px] text-[#8A3A3A]">
          {error}
        </p>
      )}

      {data && data.posts.length > 0 ? (
        <>
          <div className="overflow-x-auto rounded-xl border border-ink-100">
            <table className="w-full text-sm">
              <thead className="bg-ink-50 text-xs uppercase tracking-wide text-ink-500">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">Title</th>
                  <th className="px-4 py-2 text-left font-medium">Category</th>
                  <th className="px-4 py-2 text-left font-medium">Status</th>
                  <th className="px-4 py-2 text-left font-medium">Date</th>
                  <th className="px-4 py-2 text-right font-medium">Views</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {data.posts.map((row) => (
                  <tr key={row.id} className="hover:bg-ink-50/50">
                    <td className="px-4 py-2">
                      <Link href={`/admin/blog/edit/${row.id}`}
                            className="font-semibold text-ink-900 hover:text-primary-700">
                        {row.title}
                      </Link>
                      <div className="text-[11.5px] text-ink-400">
                        {row.locale} · /{row.slug}
                      </div>
                    </td>
                    <td className="px-4 py-2 text-ink-600">
                      {row.category?.display_name ?? "—"}
                    </td>
                    <td className="px-4 py-2">
                      <span className={`rounded-full px-2 py-0.5 text-[11.5px] font-semibold ${statusTone(row.status)}`}>
                        {STATUS_LABEL[row.status] ?? row.status}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-4 py-2 text-ink-500">{when(row)}</td>
                    <td className="px-4 py-2 text-right tabular-nums text-ink-500">
                      {row.views ?? 0}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <div className="flex items-center justify-end gap-2.5 text-[12px]">
                        {row.status === STATUS.PUBLISHED && (
                          <Link href={`/blog/${row.locale}/${row.slug}`} target="_blank"
                                className="font-semibold text-primary-700 hover:text-primary-800">
                            View
                          </Link>
                        )}
                        <button type="button" disabled={busy === row.id}
                                onClick={() => void remove(row)}
                                className="text-ink-400 hover:text-[#8A3A3A] disabled:opacity-40">
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {pages > 1 && (
            <div className="flex items-center justify-end gap-2 text-[13px]">
              <button type="button" disabled={page <= 1}
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      className="rounded-lg border border-ink-200 px-3 py-1.5 font-semibold text-ink-600 hover:bg-ink-50 disabled:opacity-40">
                Previous
              </button>
              <span className="tabular-nums text-ink-500">{page} / {pages}</span>
              <button type="button" disabled={page >= pages}
                      onClick={() => setPage((p) => p + 1)}
                      className="rounded-lg border border-ink-200 px-3 py-1.5 font-semibold text-ink-600 hover:bg-ink-50 disabled:opacity-40">
                Next
              </button>
            </div>
          )}
        </>
      ) : (
        <p className="text-sm text-ink-500">
          {isLoading ? "Loading…" : "No posts match."}
        </p>
      )}
    </div>
  );
}
