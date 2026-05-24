"use client";

import { useEffect, useState } from "react";

export type AnnouncementInput = {
  kind: "first_login" | "login_banner";
  title: string;
  body: string;
  image_url: string | null;
  cta_label: string | null;
  cta_url: string | null;
  active: boolean;
  starts_at: string | null;
  ends_at: string | null;
};

export function AnnouncementForm({
  initial, onSubmit, submitting,
}: {
  initial?: Partial<AnnouncementInput>;
  onSubmit: (data: AnnouncementInput) => void;
  submitting: boolean;
}) {
  const [form, setForm] = useState<AnnouncementInput>({
    kind: (initial?.kind as AnnouncementInput["kind"]) || "login_banner",
    title: initial?.title || "",
    body: initial?.body || "",
    image_url: initial?.image_url || null,
    cta_label: initial?.cta_label || null,
    cta_url: initial?.cta_url || null,
    active: initial?.active ?? true,
    starts_at: initial?.starts_at || null,
    ends_at: initial?.ends_at || null,
  });

  useEffect(() => {
    if (initial) {
      setForm((f) => ({ ...f, ...(initial as any) }));
    }
  }, [initial]);

  const set = <K extends keyof AnnouncementInput>(k: K, v: AnnouncementInput[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  return (
    <form
      onSubmit={(e) => { e.preventDefault(); onSubmit(form); }}
      className="space-y-3"
    >
      <Field label="Kind">
        <select
          value={form.kind}
          onChange={(e) => set("kind", e.target.value as AnnouncementInput["kind"])}
          className="w-full rounded-xl border border-ink-200 px-3 py-2 text-sm"
        >
          <option value="first_login">first_login</option>
          <option value="login_banner">login_banner</option>
        </select>
      </Field>
      <Field label="Title">
        <input
          required
          value={form.title}
          onChange={(e) => set("title", e.target.value)}
          className="w-full rounded-xl border border-ink-200 px-3 py-2 text-sm"
        />
      </Field>
      <Field label="Body">
        <textarea
          required
          value={form.body}
          onChange={(e) => set("body", e.target.value)}
          rows={6}
          className="w-full rounded-xl border border-ink-200 px-3 py-2 text-sm"
        />
      </Field>
      <Field label="Image URL (optional)">
        <input
          value={form.image_url || ""}
          onChange={(e) => set("image_url", e.target.value || null)}
          className="w-full rounded-xl border border-ink-200 px-3 py-2 text-sm"
        />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="CTA label">
          <input
            value={form.cta_label || ""}
            onChange={(e) => set("cta_label", e.target.value || null)}
            className="w-full rounded-xl border border-ink-200 px-3 py-2 text-sm"
          />
        </Field>
        <Field label="CTA URL">
          <input
            value={form.cta_url || ""}
            onChange={(e) => set("cta_url", e.target.value || null)}
            className="w-full rounded-xl border border-ink-200 px-3 py-2 text-sm"
          />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Starts at">
          <input
            type="datetime-local"
            value={form.starts_at?.slice(0, 16) || ""}
            onChange={(e) => set("starts_at", e.target.value ? new Date(e.target.value).toISOString() : null)}
            className="w-full rounded-xl border border-ink-200 px-3 py-2 text-sm"
          />
        </Field>
        <Field label="Ends at">
          <input
            type="datetime-local"
            value={form.ends_at?.slice(0, 16) || ""}
            onChange={(e) => set("ends_at", e.target.value ? new Date(e.target.value).toISOString() : null)}
            className="w-full rounded-xl border border-ink-200 px-3 py-2 text-sm"
          />
        </Field>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={form.active} onChange={(e) => set("active", e.target.checked)} />
        Active
      </label>
      <button
        type="submit"
        disabled={submitting}
        className="w-full rounded-xl bg-primary-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 disabled:opacity-50"
      >
        {submitting ? "Saving…" : "Save"}
      </button>
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-ink-500">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}
