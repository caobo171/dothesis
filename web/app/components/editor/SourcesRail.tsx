"use client";

import { useEffect } from "react";
import useSWR from "swr";

import { ExternalLink } from "lucide-react";

import { useT } from "@/app/lib/i18n/LocaleProvider";
import { tokenStore } from "@/app/lib/tokenStore";


// The endpoint returns the whole paper (`{"id": …, **ref}`), so `url` and `doi`
// were already on the wire — this rail just dropped them, and a student who
// wanted to check a source had to copy the title into a search engine.
type Reference = {
  id: string; author: string; year: string; title?: string;
  url?: string | null; doi?: string | null;
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


// POST-only read: the key is already an absolute /api/v1/… path (so it can't
// route through apiFetch, which prepends BASE), so we POST directly here and
// fold the access_token into the JSON body — keeping the JWT out of the URL.
const fetcher = (url: string) =>
  fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ access_token: tokenStore.get() }),
  }).then(r => r.json());


// Right rail. Read-only browser of the M2 reference pool. Insertion happens
// via the SelectionToolbar's Cite popover; this rail is for "what's available"
// at-a-glance.
export function SourcesRail({ projectId, highlightedId }: { projectId: string; highlightedId?: string | null }) {
  const t = useT();
  const { data } = useSWR<Reference[]>(`/api/v1/projects/${projectId}/m5/references`, fetcher);
  const refs = data ?? [];

  // Scroll the highlighted source into view when a citation is clicked.
  useEffect(() => {
    if (!highlightedId) return;
    document.getElementById(`src-${highlightedId}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [highlightedId]);

  return (
    <aside className="w-56 shrink-0 border-l border-gray-200 py-4 px-3 overflow-y-auto">
      <div className="text-xs uppercase tracking-wider text-gray-400 mb-2">
        {t("editor.sources.title", { count: refs.length })}
      </div>
      {refs.length === 0 ? (
        <div className="text-xs text-gray-500">{t("editor.sources.empty")}</div>
      ) : (
        <ul className="space-y-1">
          {refs.map(r => {
            const active = r.id === highlightedId;
            const href = _href(r);
            const body = (
              <>
                <div className="font-medium text-gray-900 flex items-center gap-1">
                  <span className="truncate">{r.author} ({r.year})</span>
                  {href && (
                    <ExternalLink className="h-3 w-3 shrink-0 text-gray-400" aria-hidden />
                  )}
                </div>
                {r.title && <div className="text-gray-500 truncate">{r.title}</div>}
              </>
            );
            return (
              <li
                key={r.id}
                id={`src-${r.id}`}
                aria-current={active ? "true" : undefined}
                className={
                  "text-xs rounded transition-colors " +
                  (active
                    ? "bg-primary-50 ring-1 ring-primary-500 text-ink-900"
                    : "text-gray-700 bg-gray-50")
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
                    className="block px-2 py-1 rounded hover:bg-primary-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                  >
                    {body}
                  </a>
                ) : (
                  <div className="px-2 py-1">{body}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}
