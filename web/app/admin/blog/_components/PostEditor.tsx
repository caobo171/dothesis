"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";

import { slugify } from "@/app/blog/_lib/markdown";
import { apiFetch, swrFetcher } from "@/app/lib/api";

import { BodyEditor } from "./BodyEditor";
import { LivePostLink, PostPreview } from "./PostPreview";
import { STATUS, type AdminPost, type Options, type CategoryRow } from "./types";

/**
 * The one form behind both /admin/blog/create and /admin/blog/edit/[id].
 *
 * The payload it builds is a SEED (`dothesis-blog-seed/1`), not a loose row:
 * /admin/blog/upsert runs it through the same `validate_seed` and duplicate
 * guard the CLI and the content engine go through, so the editor cannot put a
 * post into the bank that a seed file could not. That is deliberate — it is
 * also why this form shows the server's own rejection text instead of
 * re-implementing the rules client-side and drifting from them.
 *
 * Fields NOT offered, because the column does not exist and the value would be
 * accepted and then vanish: `sibling_slugs`, `images`, `gate_status`. All three
 * are seed-time inputs consumed when a post is written; only `image_url` (the
 * hero) survives onto BlogPost.
 */

const LOCALES = ["vi", "en"] as const;

/** The server's `normalize_slug`, to the letter: a slug that differs from it
 *  is a 422, and finding that out on save is a worse way to learn the rule. */
function normalizePostSlug(text: string): string {
  return slugify(text).slice(0, 120).replace(/-+$/, "");
}

/** Textarea ⇄ list. One per line, blanks dropped. */
function toList(text: string): string[] {
  return text.split("\n").map((s) => s.trim()).filter(Boolean);
}

function fromList(list: string[] | undefined): string {
  return (list ?? []).join("\n");
}

/** `datetime-local` wants `YYYY-MM-DDTHH:mm` with no zone. */
function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

type Form = {
  title: string;
  slug: string;
  locale: string;
  category: string;
  archetype: string;
  focus_keyword: string;
  focus_keyword_volume: string;
  secondary_keywords: string;
  tags: string;
  excerpt: string;
  meta_title: string;
  meta_description: string;
  image_url: string;
  canonical_url: string;
  body: string;
  status: string;
  published_at: string;
  scheduled_at: string;
  duplicate_override_reason: string;
};

const EMPTY: Form = {
  title: "", slug: "", locale: "vi", category: "", archetype: "",
  focus_keyword: "", focus_keyword_volume: "", secondary_keywords: "", tags: "",
  excerpt: "", meta_title: "", meta_description: "", image_url: "",
  canonical_url: "", body: "", status: String(STATUS.DRAFT),
  published_at: "", scheduled_at: "", duplicate_override_reason: "",
};

export function PostEditor({ postId }: { postId?: string }) {
  const router = useRouter();
  const [form, setForm] = useState<Form>(EMPTY);
  const [slugTouched, setSlugTouched] = useState(false);
  const [tab, setTab] = useState<"write" | "preview">("write");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [duplicate, setDuplicate] = useState(false);

  const { data: options } = useSWR<Options>("/admin/blog/options", swrFetcher);
  const { data: catData } = useSWR<{ categories: CategoryRow[] }>(
    "/admin/blog/categories/list", swrFetcher);
  const { data: post, isLoading } = useSWR<AdminPost>(
    postId ? ["/admin/blog/get", postId] : null,
    () => apiFetch("/admin/blog/get", { method: "POST", body: { id: postId } }),
  );

  // Load once, into local state: this is a form, so the server copy is the
  // starting point and not the live value.
  useEffect(() => {
    if (!post) return;
    setForm({
      title: post.title ?? "",
      slug: post.slug ?? "",
      locale: post.locale ?? "vi",
      category: post.category?.slug ?? "",
      archetype: post.archetype ?? "",
      focus_keyword: post.focus_keyword ?? "",
      focus_keyword_volume: post.focus_keyword_volume == null ? "" : String(post.focus_keyword_volume),
      secondary_keywords: fromList(post.secondary_keywords),
      tags: fromList(post.tags),
      excerpt: post.excerpt ?? "",
      meta_title: post.meta_title ?? "",
      meta_description: post.meta_description ?? "",
      image_url: post.image_url ?? "",
      canonical_url: post.canonical_url ?? "",
      body: post.body ?? "",
      status: String(post.status ?? STATUS.DRAFT),
      published_at: toLocalInput(post.published_at),
      scheduled_at: toLocalInput(post.scheduled_at),
      duplicate_override_reason: post.duplicate_override_reason ?? "",
    });
    setSlugTouched(true);   // an existing slug is a live URL; never re-derive it
  }, [post]);

  const set = (key: keyof Form, value: string) =>
    setForm((f) => ({ ...f, [key]: value }));

  // Only the categories that exist in the chosen language. The closed slug list
  // is the same in both, but a slug with no row in this locale would bind the
  // post to nothing — `category_index` is keyed on (locale, slug).
  const categories = useMemo(
    () => (catData?.categories ?? []).filter((c) => c.locale === form.locale),
    [catData, form.locale],
  );
  const categoryName = categories.find((c) => c.slug === form.category)?.display_name ?? null;

  const onTitle = (value: string) => {
    setForm((f) => ({
      ...f,
      title: value,
      // Derived until the operator takes the wheel. On an existing post it is
      // never derived: the slug is the published URL.
      slug: slugTouched ? f.slug : normalizePostSlug(value),
    }));
  };

  async function save() {
    setSaving(true);
    setError(null);
    const status = Number(form.status);
    const body: Record<string, unknown> = {
      schema: "dothesis-blog-seed/1",
      title: form.title.trim(),
      slug: form.slug.trim(),
      locale: form.locale,
      meta_title: form.meta_title.trim(),
      meta_description: form.meta_description.trim(),
      focus_keyword: form.focus_keyword.trim(),
      excerpt: form.excerpt.trim(),
      category: form.category,
      archetype: form.archetype.trim(),
      body: form.body,
      secondary_keywords: toList(form.secondary_keywords),
      tags: toList(form.tags),
      status,
      // Sent as a naive local string; the API parses it into the column's
      // timezone-aware type the same way the CLI's --at does.
      published_at: form.published_at || null,
      scheduled_at: status === STATUS.SCHEDULED ? form.scheduled_at || null : null,
      image_url: form.image_url.trim() || null,
      canonical_url: form.canonical_url.trim() || null,
      focus_keyword_volume: form.focus_keyword_volume.trim()
        ? Number(form.focus_keyword_volume)
        : null,
    };
    if (form.duplicate_override_reason.trim()) {
      body.duplicate_override_reason = form.duplicate_override_reason.trim();
    }

    try {
      const saved = (await apiFetch("/admin/blog/upsert",
        { method: "POST", body })) as AdminPost;
      router.push("/admin/blog");
      router.refresh();
      return saved;
    } catch (e) {
      const err = e as { status?: number; message?: string };
      setError(err.message || "Save failed");
      // 409 is the duplicate guard. It is overridable, but only with a written
      // reason — so the field appears exactly when it becomes relevant rather
      // than sitting on the form inviting use.
      if (err.status === 409) setDuplicate(true);
    } finally {
      setSaving(false);
    }
  }

  if (postId && isLoading) {
    return <p className="text-sm text-ink-500">Loading…</p>;
  }

  const status = Number(form.status);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-ink-900">
          {postId ? "Edit post" : "New post"}
        </h1>
        <div className="flex items-center gap-3">
          {postId && post?.slug && (
            <LivePostLink locale={form.locale} slug={post.slug} />
          )}
          <div className="flex rounded-lg border border-ink-200 p-0.5">
            {(["write", "preview"] as const).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setTab(k)}
                className={`rounded-md px-3 py-1 text-sm font-semibold capitalize ${
                  tab === k ? "bg-ink-900 text-white" : "text-ink-600 hover:bg-ink-50"
                }`}
              >
                {k}
              </button>
            ))}
          </div>
          <button
            type="button"
            disabled={saving}
            onClick={() => void save()}
            className="rounded-xl bg-primary-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 disabled:opacity-40"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-[#E6C9C9] bg-[#FBF0F0] px-3 py-2 text-[13px] text-[#8A3A3A]">
          {error}
        </div>
      )}

      {tab === "preview" ? (
        <div className="rounded-xl border border-ink-100 bg-white p-2">
          <PostPreview
            title={form.title}
            body={form.body}
            locale={form.locale}
            imageUrl={form.image_url}
            categoryName={categoryName}
            publishedAt={form.published_at || null}
          />
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          {/* --- the prose ------------------------------------------------ */}
          <div className="space-y-3">
            <Field label="Title">
              <input className={INPUT} value={form.title}
                     onChange={(e) => onTitle(e.target.value)} />
            </Field>

            <Field label="Slug" hint="ASCII, lowercase, hyphenated — the published URL.">
              <input className={INPUT} value={form.slug}
                     onChange={(e) => { setSlugTouched(true); set("slug", e.target.value); }}
                     onBlur={(e) => set("slug", normalizePostSlug(e.target.value))} />
            </Field>

            <Field label="Excerpt">
              <textarea className={INPUT} rows={2} value={form.excerpt}
                        onChange={(e) => set("excerpt", e.target.value)} />
            </Field>

            <BodyEditor value={form.body} onChange={(md) => set("body", md)} />
          </div>

          {/* --- everything that is not the prose -------------------------- */}
          <div className="space-y-3">
            <Panel title="Publishing">
              <Field label="Status">
                <select className={INPUT} value={form.status}
                        onChange={(e) => set("status", e.target.value)}>
                  <option value={STATUS.DRAFT}>Draft</option>
                  <option value={STATUS.PUBLISHED}>Published</option>
                  <option value={STATUS.SCHEDULED}>Scheduled</option>
                </select>
              </Field>
              {status === STATUS.SCHEDULED && (
                <Field label="Goes live at"
                       hint="The scheduler publishes it; until then it is invisible.">
                  <input type="datetime-local" className={INPUT} value={form.scheduled_at}
                         onChange={(e) => set("scheduled_at", e.target.value)} />
                </Field>
              )}
              <Field label="Published at" hint="Shown on the article. Blank = now, on publish.">
                <input type="datetime-local" className={INPUT} value={form.published_at}
                       onChange={(e) => set("published_at", e.target.value)} />
              </Field>
            </Panel>

            <Panel title="Placement">
              <Field label="Locale">
                <select className={INPUT} value={form.locale}
                        onChange={(e) => { set("locale", e.target.value); set("category", ""); }}>
                  {LOCALES.map((l) => <option key={l} value={l}>{l}</option>)}
                </select>
              </Field>
              <Field label="Category"
                     hint={categories.length ? undefined
                       : "No categories exist for this locale yet — create one first."}>
                <select className={INPUT} value={form.category}
                        onChange={(e) => set("category", e.target.value)}>
                  <option value="">—</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.slug}>{c.display_name} ({c.slug})</option>
                  ))}
                </select>
              </Field>
              <Field label="Archetype">
                <input className={INPUT} list="blog-archetypes" value={form.archetype}
                       onChange={(e) => set("archetype", e.target.value)} />
                <datalist id="blog-archetypes">
                  {(options?.archetypes ?? []).map((a) => <option key={a} value={a} />)}
                </datalist>
              </Field>
            </Panel>

            <Panel title="Search">
              <Field label="Meta title"><input className={INPUT} value={form.meta_title}
                     onChange={(e) => set("meta_title", e.target.value)} /></Field>
              <Field label="Meta description">
                <textarea className={INPUT} rows={3} value={form.meta_description}
                          onChange={(e) => set("meta_description", e.target.value)} />
              </Field>
              <Field label="Focus keyword"><input className={INPUT} value={form.focus_keyword}
                     onChange={(e) => set("focus_keyword", e.target.value)} /></Field>
              <Field label="Focus keyword volume" hint="Blank when unmeasured.">
                <input className={INPUT} inputMode="numeric" value={form.focus_keyword_volume}
                       onChange={(e) => set("focus_keyword_volume", e.target.value)} />
              </Field>
              <Field label="Secondary keywords" hint="One per line.">
                <textarea className={INPUT} rows={3} value={form.secondary_keywords}
                          onChange={(e) => set("secondary_keywords", e.target.value)} />
              </Field>
              <Field label="Canonical URL" hint="Only when this page duplicates another.">
                <input className={INPUT} value={form.canonical_url}
                       onChange={(e) => set("canonical_url", e.target.value)} />
              </Field>
            </Panel>

            <Panel title="Media & tags">
              <Field label="Hero image URL"><input className={INPUT} value={form.image_url}
                     onChange={(e) => set("image_url", e.target.value)} /></Field>
              <Field label="Tags" hint="One per line.">
                <textarea className={INPUT} rows={3} value={form.tags}
                          onChange={(e) => set("tags", e.target.value)} />
              </Field>
            </Panel>

            {duplicate && (
              <Panel title="Duplicate override">
                <Field
                  label="Reason"
                  hint="The guard blocked this as too close to an existing post. Saying why is what makes publishing anyway a decision on the record."
                >
                  <textarea className={INPUT} rows={3} value={form.duplicate_override_reason}
                            onChange={(e) => set("duplicate_override_reason", e.target.value)} />
                </Field>
              </Panel>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

const INPUT =
  "w-full rounded-lg border border-ink-200 px-3 py-2 text-sm text-ink-900 " +
  "focus:border-primary-400 focus:outline-none";

function Field({ label, hint, children }: {
  label: string; hint?: string; children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1">
      <span className="text-[12px] font-semibold uppercase tracking-wide text-ink-500">
        {label}
      </span>
      {children}
      {hint && <span className="block text-[11.5px] text-ink-400">{hint}</span>}
    </label>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3 rounded-xl border border-ink-100 bg-white p-3">
      <h2 className="text-[13px] font-bold text-ink-900">{title}</h2>
      {children}
    </section>
  );
}
