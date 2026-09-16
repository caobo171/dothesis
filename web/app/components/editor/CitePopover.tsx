"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useSWRConfig } from "swr";
import { ArrowLeftIcon, BookOpenIcon, ChevronDownIcon, CheckCircleIcon, MagnifyingGlassIcon } from "@heroicons/react/24/outline";
import { ExternalLink } from "lucide-react";
import { apiFetch } from "@/app/lib/api";

type Reference = { id: string; author: string; authors?: string[]; year: string | number; title?: string; venue?: string; doi?: string; doi_available?: boolean; url?: string; abstract?: string; abstract_preview?: string; citation_count?: number; verified?: boolean; provider?: string; ambiguous?: boolean };
type Props = { projectId: string; selectedText?: string; onSelect: (referenceId: string) => void; onClose: () => void };

function sourceHref(paper: Reference): string | null {
  const url = String(paper.url ?? "").trim();
  if (/^https?:\/\//i.test(url)) return url;
  const doi = String(paper.doi ?? "").trim();
  return doi ? (/^https?:\/\//i.test(doi) ? doi : `https://doi.org/${doi.replace(/^doi:\s*/i, "")}`) : null;
}
function paperAbstract(paper: Reference) { return String(paper.abstract ?? paper.abstract_preview ?? "").trim(); }
function paperVenue(paper: Reference) { const venue = String(paper.venue ?? "").trim(); return /^(openalex|crossref|semantic scholar)$/i.test(venue) ? "" : venue; }

export function CitePopover({ projectId, selectedText = "", onSelect, onClose }: Props) {
  const { mutate } = useSWRConfig();
  const [refs, setRefs] = useState<Reference[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [mode, setMode] = useState<"library" | "search">("library");
  // Selection seeds discovery only. It must not invisibly filter the library.
  const [libraryQuery, setLibraryQuery] = useState("");
  const [searchQuery, setSearchQuery] = useState(selectedText.trim().slice(0, 280));
  const [results, setResults] = useState<Reference[]>([]);
  const [hasSearched, setHasSearched] = useState(false);
  const [providers, setProviders] = useState<string[]>([]);
  const [searching, setSearching] = useState(false);
  const [addingId, setAddingId] = useState<string | null>(null);
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const searchRequest = useRef(0);

  useEffect(() => {
    let cancelled = false;
    setRefs(null); setLoadError(null);
    apiFetch(`/projects/${projectId}/m5/references`, { method: "POST" })
      .then((data: any) => { if (!cancelled) setRefs(Array.isArray(data) ? data : []); })
      .catch((e) => { if (!cancelled) setLoadError(e instanceof Error ? e.message : "Không thể tải thư viện nguồn."); });
    return () => { cancelled = true; searchRequest.current += 1; };
  }, [projectId]);
  useEffect(() => { const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); }; window.addEventListener("keydown", onKey); return () => window.removeEventListener("keydown", onKey); }, [onClose]);

  const filtered = useMemo(() => (refs ?? []).filter(r => {
    const q = libraryQuery.trim().toLowerCase();
    return !q || [r.author, r.year, r.title, r.venue, r.doi].some(value => String(value ?? "").toLowerCase().includes(q));
  }), [refs, libraryQuery]);
  const search = async () => {
    const query = searchQuery.trim(); if (query.length < 3) return;
    const request = ++searchRequest.current;
    setSearching(true); setError(null); setHasSearched(true);
    try {
      const data: any = await apiFetch(`/projects/${projectId}/m5/references/search`, { method: "POST", body: { query, limit: 10 } });
      if (request !== searchRequest.current) return;
      setResults(Array.isArray(data?.results) ? data.results : []); setProviders(Array.isArray(data?.providers) ? data.providers : []);
    } catch (e) { if (request === searchRequest.current) setError(e instanceof Error ? e.message : "Không thể tìm nguồn lúc này.");
    } finally { if (request === searchRequest.current) setSearching(false); }
  };
  const savePaper = async (paper: Reference, cite: boolean) => {
    if (addingId) return;
    setAddingId(paper.id); setError(null);
    try {
      const added: any = await apiFetch(`/projects/${projectId}/m5/references/add`, { method: "POST", body: { doi: paper.doi || null, title: paper.title || null } });
      if (!added?.id) throw new Error("Không thể lưu nguồn này.");
      setRefs(current => current && !current.some(item => item.id === added.id) ? [...current, added] : current);
      setSavedIds(current => new Set(current).add(paper.id).add(added.id));
      void mutate(`/api/v1/projects/${projectId}/m5/references`);
      if (cite) { onSelect(added.id); onClose(); }
    } catch (e) { setError(e instanceof Error ? e.message : "Không thể xác minh và thêm nguồn này.");
    } finally { setAddingId(null); }
  };
  const visible = mode === "library" ? filtered : results;
  const query = mode === "library" ? libraryQuery : searchQuery;
  const setQuery = mode === "library" ? setLibraryQuery : setSearchQuery;

  return <div role="dialog" aria-label="Insert citation" className="z-50 w-[480px] max-w-[calc(100vw-2rem)] overflow-hidden rounded-2xl border border-ink-100 bg-white shadow-[0_22px_65px_rgba(24,31,50,0.22)]">
    <div className="border-b border-ink-100 px-4 pb-3 pt-3"><div className="mb-3 flex items-center gap-2"><button type="button" onClick={onClose} aria-label="Back" className="rounded-lg p-1.5 text-ink-500 transition hover:bg-ink-50 hover:text-ink-900"><ArrowLeftIcon className="h-4 w-4" /></button><BookOpenIcon className="h-4 w-4 text-primary-600" /><div className="text-sm font-semibold text-ink-900">Cite a source</div><span className="ml-auto text-[11px] text-ink-400">{refs?.length ?? 0} in library</span></div>
      <div className="mb-3 grid grid-cols-2 rounded-xl bg-ink-50 p-1 text-xs font-semibold"><button type="button" onClick={() => setMode("library")} className={`rounded-lg px-3 py-2 transition ${mode === "library" ? "bg-white text-ink-900 shadow-sm" : "text-ink-500 hover:text-ink-800"}`}>My library</button><button type="button" onClick={() => setMode("search")} className={`rounded-lg px-3 py-2 transition ${mode === "search" ? "bg-white text-ink-900 shadow-sm" : "text-ink-500 hover:text-ink-800"}`}>Find papers</button></div>
      <div className="flex gap-2"><label className="relative block flex-1"><MagnifyingGlassIcon className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" /><input type="text" autoFocus value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && mode === "search") void search(); }} placeholder={mode === "search" ? "Search by claim, topic, title or DOI…" : "Search your library…"} className="h-10 w-full rounded-xl border border-ink-200 bg-white pl-9 pr-3 text-sm outline-none transition focus:border-primary-400 focus:ring-2 focus:ring-primary-100" /></label>{mode === "search" && <button type="button" disabled={searching || searchQuery.trim().length < 3} onClick={() => void search()} className="rounded-xl bg-primary-600 px-4 text-sm font-semibold text-white transition hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50">{searching ? "Searching…" : "Search"}</button>}</div>
      {mode === "search" && <p className="mt-2 text-[10px] leading-4 text-ink-400">{providers.length ? `Indexed by ${providers.join(" + ")} · relevance to search` : "Check the abstract before deciding whether this source supports the claim."}</p>}</div>
    <div className="max-h-[440px] overflow-y-auto p-3">{error && <div role="alert" className="mb-2 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div>}{mode === "library" && refs === null && !loadError && <PaperSkeleton />}{loadError && <Empty text={`${loadError} Try again by closing and reopening this picker.`} />}{mode === "library" && refs !== null && !loadError && refs.length === 0 && <Empty text="Thư viện chưa có nguồn. Chuyển sang Find papers để tìm và lưu paper." />}{mode === "library" && refs !== null && !loadError && refs.length > 0 && filtered.length === 0 && <Empty text="No matching sources in your library." />}{mode === "search" && !searching && !hasSearched && <Empty text="Nhập claim hoặc chủ đề rồi chọn Search. Đoạn văn đã chọn chỉ được dùng để gợi ý truy vấn." />}{mode === "search" && !searching && hasSearched && results.length === 0 && !error && <Empty text="Không tìm thấy paper cho truy vấn này. Thử rút ngắn hoặc dùng từ khóa khác." />}{searching && <PaperSkeleton />}{!searching && visible.length > 0 && <ul className="space-y-2">{visible.map(paper => { const saved = savedIds.has(paper.id) || Boolean(refs?.some(ref => ref.id === paper.id || (paper.doi && ref.doi === paper.doi))); return <PaperCard key={paper.id} paper={paper} saved={saved} searchResult={mode === "search"} expanded={expanded.has(paper.id)} onToggle={() => setExpanded(current => { const next = new Set(current); next.has(paper.id) ? next.delete(paper.id) : next.add(paper.id); return next; })} actions={mode === "library" ? <button type="button" disabled={paper.ambiguous} onClick={() => { onSelect(paper.id); onClose(); }} className="rounded-lg bg-primary-50 px-2.5 py-1.5 text-[11px] font-semibold text-primary-700 transition hover:bg-primary-100 disabled:cursor-not-allowed disabled:opacity-50">Cite</button> : <><button type="button" disabled={addingId !== null || saved} onClick={() => void savePaper(paper, false)} className="rounded-lg border border-ink-200 px-2.5 py-1.5 text-[11px] font-semibold text-ink-700 disabled:opacity-50">{addingId === paper.id ? "Saving…" : saved ? "Saved" : "Save"}</button><button type="button" disabled={addingId !== null} onClick={() => void savePaper(paper, true)} className="rounded-lg bg-primary-600 px-2.5 py-1.5 text-[11px] font-semibold text-white disabled:opacity-50">Cite</button></>} />; })}</ul>}</div>
  </div>;
}

function PaperCard({ paper, saved = false, searchResult = false, expanded, onToggle, actions }: { paper: Reference; saved?: boolean; searchResult?: boolean; expanded: boolean; onToggle: () => void; actions: React.ReactNode }) { const abstract = paperAbstract(paper); const href = sourceHref(paper); const venue = paperVenue(paper); return <li className="rounded-xl border border-ink-100 bg-white p-3"><div className="text-sm font-semibold leading-5 text-ink-900">{paper.title || `${paper.author} (${paper.year})`}</div><div className="mt-1 text-[11px] text-ink-500">{paper.author} · {paper.year}{venue ? ` · ${venue}` : ""}</div>{abstract && <div className="mt-2"><div className={`text-[11px] leading-[1.55] text-ink-500 ${expanded ? "" : "line-clamp-3"}`}><span className="mr-1 font-semibold uppercase tracking-wide text-ink-400">Abstract</span>{abstract}</div><button type="button" onClick={onToggle} className="mt-1 inline-flex items-center gap-0.5 text-[10px] font-semibold text-primary-700 hover:underline">{expanded ? "Show less" : "See abstract"}<ChevronDownIcon className={`h-3 w-3 transition ${expanded ? "rotate-180" : ""}`} /></button></div>}<div className="mt-2 flex flex-wrap items-center gap-2 text-[10px]">{paper.doi && <span className="text-ink-500">{searchResult ? "DOI available" : "DOI"}</span>}{paper.verified && <span className="inline-flex items-center gap-1 text-emerald-700"><CheckCircleIcon className="h-3.5 w-3.5" />Metadata verified</span>}{saved && <span role="status" className="text-emerald-700">Saved to library</span>}{paper.ambiguous && <span className="text-amber-700">Choose a distinct paper before citing</span>}{paper.provider && <span className="text-ink-400">Indexed by {paper.provider}</span>}{href && <a href={href} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-primary-700 hover:underline">Open source <ExternalLink className="h-3 w-3" /></a>}</div><div className="mt-3 flex items-center justify-end gap-2">{actions}</div></li>; }
function Empty({ text }: { text: string }) { return <div className="px-5 py-10 text-center text-xs leading-5 text-ink-500"><BookOpenIcon className="mx-auto mb-2 h-5 w-5 text-ink-300" />{text}</div>; }
function PaperSkeleton() { return <div className="space-y-2" aria-label="Loading papers">{[0, 1, 2].map(i => <div key={i} className="animate-pulse rounded-xl border border-ink-100 p-3"><div className="h-3.5 w-4/5 rounded bg-ink-100" /><div className="mt-2 h-2.5 w-2/5 rounded bg-ink-100" /><div className="mt-3 h-2.5 w-full rounded bg-ink-50" /></div>)}</div>; }
