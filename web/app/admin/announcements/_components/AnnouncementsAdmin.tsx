"use client";

import { useState } from "react";
import useSWR, { mutate as globalMutate } from "swr";

import { Drawer } from "@/app/components/admin/Drawer";
import { apiFetch, swrFetcher } from "@/app/lib/api";

import { AnnouncementForm, type AnnouncementInput } from "./AnnouncementForm";

type AnnouncementRow = {
  id: string;
  kind: string;
  title: string;
  body: string;
  image_url: string | null;
  cta_label: string | null;
  cta_url: string | null;
  active: boolean;
  starts_at: string | null;
  ends_at: string | null;
  created_at: string | null;
};

type ListResp = { items: AnnouncementRow[]; total: number };

const KEY = "/admin/announcements";

export default function AnnouncementsAdmin() {
  const { data } = useSWR<ListResp>(KEY, swrFetcher);
  const [editing, setEditing] = useState<AnnouncementRow | "new" | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function save(form: AnnouncementInput) {
    setSubmitting(true);
    try {
      if (editing === "new") {
        await apiFetch(KEY, { method: "POST", body: form });
      } else if (editing) {
        await apiFetch(`${KEY}/${editing.id}`, { method: "PATCH", body: form });
      }
      setEditing(null);
      globalMutate(KEY);
    } finally {
      setSubmitting(false);
    }
  }

  async function remove(id: string) {
    if (!confirm("Delete this announcement?")) return;
    await apiFetch(`${KEY}/${id}`, { method: "DELETE" });
    globalMutate(KEY);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-ink-900">Announcements</h1>
        <button
          type="button"
          onClick={() => setEditing("new")}
          className="rounded-xl bg-primary-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary-700"
        >
          + New
        </button>
      </div>

      <div className="grid gap-3">
        {(data?.items || []).map((a) => (
          <div key={a.id} className="rounded-2xl border border-ink-100 bg-white p-4 shadow-sm">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="rounded-full bg-primary-50 px-2 py-0.5 text-xs font-semibold text-primary-600">{a.kind}</span>
                  {!a.active && <span className="rounded-full bg-ink-100 px-2 py-0.5 text-xs text-ink-500">inactive</span>}
                </div>
                <h3 className="mt-2 text-base font-semibold text-ink-900">{a.title}</h3>
                <p className="mt-1 text-sm text-ink-500 line-clamp-2">{a.body}</p>
              </div>
              <div className="flex gap-2 flex-shrink-0">
                <button type="button" onClick={() => setEditing(a)} className="text-sm text-primary-600 hover:underline">
                  Edit
                </button>
                <button type="button" onClick={() => remove(a.id)} className="text-sm text-red-600 hover:underline">
                  Delete
                </button>
              </div>
            </div>
          </div>
        ))}
        {data && data.items.length === 0 && (
          <div className="rounded-2xl border border-dashed border-ink-200 p-8 text-center text-sm text-ink-500">
            No announcements yet.
          </div>
        )}
      </div>

      <Drawer
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "New announcement" : "Edit announcement"}
      >
        {editing && (
          <AnnouncementForm
            initial={editing === "new" ? undefined : {
              ...editing,
              kind: editing.kind as AnnouncementInput["kind"],
            }}
            onSubmit={save}
            submitting={submitting}
          />
        )}
      </Drawer>
    </div>
  );
}
