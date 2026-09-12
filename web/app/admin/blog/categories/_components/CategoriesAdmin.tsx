"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";

import { apiFetch, swrFetcher } from "@/app/lib/api";

import type { CategoryRow, Options } from "../../_components/types";

/**
 * The hubs, in every language edition at once.
 *
 * A category is one row per (locale, slug): `spss` in Vietnamese and `spss` in
 * English are two rows sharing a URL segment, and the intro copy on each is the
 * only content that hub page has of its own. Seeing them side by side is the
 * point — the failure this screen exists to make visible is an English post
 * landing with no English hub to sit in.
 *
 * The slug list is CLOSED (app/blog/seeds.py §6). A category is supposed to
 * exist only once its own name has measured search volume, so this screen adds
 * the missing LANGUAGE EDITION of a known hub; it cannot invent a tenth
 * category, and the server refuses if it tries.
 */

const LOCALES = ["vi", "en"] as const;

type Draft = {
  id?: string;
  locale: string;
  slug: string;
  name: string;
  display_name: string;
  intro_md: string;
  sort_order: string;
};

const EMPTY: Draft = {
  locale: "vi", slug: "", name: "", display_name: "", intro_md: "", sort_order: "0",
};

export default function CategoriesAdmin() {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data, mutate, isLoading } =
    useSWR<{ categories: CategoryRow[] }>("/admin/blog/categories/list", swrFetcher);
  const { data: options } = useSWR<Options>("/admin/blog/options", swrFetcher);

  const rows = data?.categories ?? [];
  const set = (key: keyof Draft, value: string) =>
    setDraft((d) => (d ? { ...d, [key]: value } : d));

  async function save() {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      await apiFetch("/admin/blog/categories/upsert", {
        method: "POST",
        body: {
          locale: draft.locale,
          slug: draft.slug,
          name: draft.name.trim(),
          display_name: draft.display_name.trim(),
          intro_md: draft.intro_md.trim() || null,
          sort_order: Number(draft.sort_order) || 0,
        },
      });
      setDraft(null);
      void mutate();
    } catch (e) {
      setError((e as Error)?.message || "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function remove(row: CategoryRow) {
    if (!window.confirm(`Delete the ${row.locale} edition of “${row.slug}”?`)) return;
    setError(null);
    try {
      await apiFetch("/admin/blog/categories/delete",
        { method: "POST", body: { id: row.id } });
      void mutate();
    } catch (e) {
      // The server refuses while posts still point at it, and says how many.
      // Surfacing its sentence beats inventing a vaguer one here.
      setError((e as Error)?.message || "Delete failed");
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-ink-900">Blog categories</h1>
        <div className="flex items-center gap-2">
          <Link href="/admin/blog"
                className="rounded-xl border border-ink-200 px-3 py-2 text-sm font-semibold text-ink-700 hover:bg-ink-50">
            Posts
          </Link>
          <button type="button" onClick={() => setDraft(EMPTY)}
                  className="rounded-xl bg-primary-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary-700">
            Add edition
          </button>
        </div>
      </div>

      {error && (
        <p className="rounded-lg border border-[#E6C9C9] bg-[#FBF0F0] px-3 py-2 text-[13px] text-[#8A3A3A]">
          {error}
        </p>
      )}

      {draft && (
        <section className="space-y-3 rounded-xl border border-ink-200 bg-white p-4">
          <h2 className="text-sm font-bold text-ink-900">
            {draft.id ? "Edit category" : "Add a language edition"}
          </h2>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block space-y-1">
              <span className={LABEL}>Locale</span>
              <select className={INPUT} value={draft.locale} disabled={Boolean(draft.id)}
                      onChange={(e) => set("locale", e.target.value)}>
                {LOCALES.map((l) => <option key={l} value={l}>{l}</option>)}
              </select>
            </label>
            <label className="block space-y-1">
              <span className={LABEL}>Slug</span>
              <select className={INPUT} value={draft.slug} disabled={Boolean(draft.id)}
                      onChange={(e) => set("slug", e.target.value)}>
                <option value="">—</option>
                {(options?.category_slugs ?? []).map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
              <span className="block text-[11.5px] text-ink-400">
                Closed list. A new category is a code change, not an entry here.
              </span>
            </label>
            <label className="block space-y-1">
              <span className={LABEL}>Name</span>
              <input className={INPUT} value={draft.name}
                     onChange={(e) => set("name", e.target.value)} />
            </label>
            <label className="block space-y-1">
              <span className={LABEL}>Display name</span>
              <input className={INPUT} value={draft.display_name}
                     onChange={(e) => set("display_name", e.target.value)} />
            </label>
            <label className="block space-y-1">
              <span className={LABEL}>Sort order</span>
              <input className={INPUT} inputMode="numeric" value={draft.sort_order}
                     onChange={(e) => set("sort_order", e.target.value)} />
            </label>
          </div>
          <label className="block space-y-1">
            <span className={LABEL}>Intro (markdown)</span>
            <textarea className={INPUT} rows={6} value={draft.intro_md}
                      onChange={(e) => set("intro_md", e.target.value)} />
            <span className="block text-[11.5px] text-ink-400">
              300–500 words, written in this language rather than translated — it is
              the only content the hub page has of its own.
            </span>
          </label>
          <div className="flex items-center gap-2">
            <button type="button" disabled={busy || !draft.slug} onClick={() => void save()}
                    className="rounded-xl bg-primary-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 disabled:opacity-40">
              {busy ? "Saving…" : "Save"}
            </button>
            <button type="button" onClick={() => setDraft(null)}
                    className="text-sm font-semibold text-ink-500 hover:text-ink-800">
              Cancel
            </button>
          </div>
        </section>
      )}

      {rows.length > 0 ? (
        <div className="overflow-x-auto rounded-xl border border-ink-100">
          <table className="w-full text-sm">
            <thead className="bg-ink-50 text-xs uppercase tracking-wide text-ink-500">
              <tr>
                <th className="px-4 py-2 text-left font-medium">Locale</th>
                <th className="px-4 py-2 text-left font-medium">Slug</th>
                <th className="px-4 py-2 text-left font-medium">Display name</th>
                <th className="px-4 py-2 text-left font-medium">Intro</th>
                <th className="px-4 py-2 text-right font-medium">Order</th>
                <th className="px-4 py-2 text-right font-medium">Posts</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100">
              {rows.map((row) => (
                <tr key={row.id} className="hover:bg-ink-50/50">
                  <td className="px-4 py-2 text-ink-600">{row.locale}</td>
                  <td className="px-4 py-2 font-semibold text-ink-900">{row.slug}</td>
                  <td className="px-4 py-2 text-ink-600">{row.display_name}</td>
                  <td className="px-4 py-2 text-ink-500">
                    {row.intro_md
                      ? `${row.intro_md.trim().split(/\s+/).length} words`
                      : <span className="text-[#8E6B2A]">missing</span>}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums text-ink-500">
                    {row.sort_order}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums text-ink-500">
                    {row.post_count}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <div className="flex items-center justify-end gap-2.5 text-[12px]">
                      <button
                        type="button"
                        onClick={() => setDraft({
                          id: row.id, locale: row.locale, slug: row.slug, name: row.name,
                          display_name: row.display_name, intro_md: row.intro_md ?? "",
                          sort_order: String(row.sort_order),
                        })}
                        className="font-semibold text-primary-700 hover:text-primary-800"
                      >
                        Edit
                      </button>
                      {/* Offered even when occupied: the server's refusal names
                          the count, which is more useful than a disabled button
                          that explains nothing. */}
                      <button type="button" onClick={() => void remove(row)}
                              className="text-ink-400 hover:text-[#8A3A3A]">
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sm text-ink-500">{isLoading ? "Loading…" : "No categories yet."}</p>
      )}
    </div>
  );
}

const INPUT =
  "w-full rounded-lg border border-ink-200 px-3 py-2 text-sm text-ink-900 " +
  "focus:border-primary-400 focus:outline-none disabled:bg-ink-50 disabled:text-ink-500";
const LABEL = "text-[12px] font-semibold uppercase tracking-wide text-ink-500";
