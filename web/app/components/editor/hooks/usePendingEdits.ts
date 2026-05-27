import { useCallback } from "react";
import useSWR from "swr";


const fetcher = async (url: string) => {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
};


type Params = { projectId: string; chapterName: string };


type AcceptResult = { conflict: boolean; chapter?: any; editId: string };


export function usePendingEdits({ projectId, chapterName }: Params) {
  const url = `/api/v1/projects/${projectId}/m5/chapters/${chapterName}`;
  const { data, mutate } = useSWR(url, fetcher, { dedupingInterval: 0 });
  const pendingEdits = (data?.pending_edits ?? []) as any[];

  const acceptEdit = useCallback(async (editId: string): Promise<AcceptResult> => {
    const r = await fetch(`${url}/pending/${editId}/accept`, { method: "POST" });
    if (r.status === 409) {
      return { conflict: true, editId };
    }
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const chapter = await r.json();
    await mutate(chapter, { revalidate: false });
    return { conflict: false, chapter, editId };
  }, [url, mutate]);

  const rejectEdit = useCallback(async (editId: string) => {
    const r = await fetch(`${url}/pending/${editId}/reject`, { method: "POST" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const chapter = await r.json();
    await mutate(chapter, { revalidate: false });
    return chapter;
  }, [url, mutate]);

  return { chapter: data, pendingEdits, acceptEdit, rejectEdit, refresh: () => mutate() };
}
