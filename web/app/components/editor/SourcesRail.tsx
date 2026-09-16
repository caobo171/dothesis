"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";

import { ExternalLink, Search, BookOpen, Link2 } from "lucide-react";

import { useT } from "@/app/lib/i18n/LocaleProvider";
import { tokenStore } from "@/app/lib/tokenStore";


// The endpoint returns the whole paper (`{"id": …, **ref}`), so `url` and `doi`
// were already on the wire — this rail just dropped them, and a student who
// wanted to check a source had to copy the title into a search engine.
type Reference = {
  id: string; author: string; year: string; title?: string;
  url?: string | null; doi?: string | null;
  abstract?: string | null; abstract_preview?: string | null;
  venue?: string | null; verified?: boolean; provider?: string | null;
};


/** A link to the paper itself, from whichever identifier the source carries. */
function _href(r: Reference): string | null {
  const url = (r.url || "").trim();
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  const doi = (r.doi || "").trim();
  // A bare DOI is not a URL; resolve it through doi.org.
  if (doi) return `https://doi.org/${doi.replace(/^https?:\/\/doi\.org\//i, "")}`;
  return null;
}

function _venue(r: Reference): string | null {
  const venue = (r.venue || "").trim();
  // Older imported rows stored the index name in `venue`. It is provenance,
  // not a journal, so never present it as publication metadata.
  return /^(openalex|crossref|semantic scholar)$/i.test(venue) ? null : venue || null;
}


// POST-only read: the key is already an absolute /api/v1/… path (so it can't
// route through apiFetch, which prepends BASE), so we POST directly here and
// fold the access_token into the JSON body — keeping the JWT out of the URL.
const fetcher = async (url: string) => {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ access_token: tokenStore.get() }),
  });
  if (!response.ok) throw new Error(`Không thể tải nguồn (HTTP ${response.status}).`);
  return response.json();
};


// Right rail. Read-only browser of the M2 reference pool. Insertion happens
// via the SelectionToolbar's Cite popover; this rail is for "what's available"
// at-a-glance.
export function SourcesRail({ projectId, highlightedId, embedded = false }: { projectId: string; highlightedId?: string | null; embedded?: boolean }) {
  const t = useT();
  const { data, error } = useSWR<Reference[]>(`/api/v1/projects/${projectId}/m5/references`, fetcher);
  const refs = data ?? [];
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return refs;
    return refs.filter(r => [r.author, r.year, r.title, r.doi]
      .some(value => String(value ?? "").toLowerCase().includes(q)));
  }, [refs, query]);

  // Scroll the highlighted source into view when a citation is clicked.
  useEffect(() => {
    if (!highlightedId) return;
    document.getElementById(`src-${highlightedId}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [highlightedId]);

  return (
    <aside className={(embedded ? "h-full w-full" : "editor-sources-rail w-[292px] shrink-0 border-l") + " overflow-y-auto border-ink-100 bg-[#fbfbfa] px-4 py-5"}>
      <div className="mb-4 flex items-start justify-between">
        <div>
          <div className="text-[11px] font-semibold tracking-[0.08em] text-ink-400">RESEARCH</div>
          <h2 className="mt-0.5 text-sm font-semibold text-ink-900">
            {t("editor.sources.title", { count: refs.length })}
          </h2>
        </div>
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary-50 text-primary-700">
          <BookOpen className="h-4 w-4" aria-hidden />
        </span>
      </div>
      <label className="relative mb-4 block">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-400" aria-hidden />
        <span className="sr-only">Search sources</span>
        <input
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder="Search sources…"
          className="h-9 w-full rounded-lg border border-ink-200 bg-white pl-8 pr-3 text-xs text-ink-800 outline-none transition focus:border-primary-400 focus:ring-2 focus:ring-primary-100"
        />
      </label>
      {error ? (
        <div role="alert" className="rounded-xl border border-red-100 bg-red-50 px-4 py-4 text-xs leading-5 text-red-700">Không thể tải thư viện nguồn. Đóng và mở lại panel để thử lại.</div>
      ) : refs.length === 0 ? (
        <div className="rounded-xl border border-dashed border-ink-200 bg-white px-4 py-8 text-center">
          <BookOpen className="mx-auto mb-2 h-5 w-5 text-ink-300" aria-hidden />
          <div className="text-xs leading-5 text-ink-500">{t("editor.sources.empty")}</div>
        </div>
      ) : filtered.length === 0 ? (
        <div className="py-8 text-center text-xs text-ink-400">No matching sources</div>
      ) : (
        <ul className="space-y-2">
          {filtered.map(r => {
            const active = r.id === highlightedId;
            const href = _href(r);
            const body = (
              <>
                <div className="flex items-start justify-between gap-2">
                  <span className="line-clamp-2 font-semibold leading-4 text-ink-900">{r.author} ({r.year})</span>
                  {href && (
                    <ExternalLink className="mt-0.5 h-3 w-3 shrink-0 text-ink-400" aria-hidden />
                  )}
                </div>
                {r.title && <div className="mt-1 line-clamp-3 leading-[1.45] text-ink-500">{r.title}</div>}
                {_venue(r) && <div className="mt-1 text-[10px] text-ink-400">{_venue(r)}</div>}
                {(r.abstract || r.abstract_preview) && <div className="mt-2 line-clamp-3 text-[10px] leading-[1.5] text-ink-500"><span className="mr-1 font-semibold uppercase tracking-wide text-ink-400">Abstract</span>{r.abstract || r.abstract_preview}</div>}
                <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px]">
                  {r.doi && <span className="inline-flex items-center gap-1 text-ink-500"><Link2 className="h-3 w-3" aria-hidden />DOI</span>}
                  {r.verified && <span className="text-emerald-700">Metadata verified</span>}
                  {href && <span className="font-medium text-primary-600">Open source</span>}
                </div>
              </>
            );
            return (
              <li
                key={r.id}
                id={`src-${r.id}`}
                aria-current={active ? "true" : undefined}
                className={
                  "overflow-hidden rounded-xl border bg-white text-xs transition-all duration-200 " +
                  (active
                    ? "border-primary-400 shadow-[0_5px_18px_rgba(28,46,255,0.10)] ring-2 ring-primary-100"
                    : "border-ink-100 text-gray-700 hover:-translate-y-px hover:border-ink-200 hover:shadow-sm")
                }
              >
                {/* New tab, and noreferrer: the editor holds unsaved prose, so
                    navigating this one away is the one thing this rail must not
                    do. */}
                {href ? (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    title={t("editor.sources.open")}
                    className="block p-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500"
                  >
                    {body}
                  </a>
                ) : (
                  <div className="p-3">{body}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}
