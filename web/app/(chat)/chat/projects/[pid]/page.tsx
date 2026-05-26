"use client";

import { useEffect } from "react";
import useSWR from "swr";
import { useParams, useRouter } from "next/navigation";


const fetcher = async (url: string) => {
  const res = await fetch(`/api/v1${url}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};


export default function ProjectIndex() {
  const router = useRouter();
  const params = useParams<{ pid: string }>();
  const { data: threads } = useSWR<Array<{ id: string }>>(
    `/projects/${params.pid}/threads`, fetcher,
  );

  useEffect(() => {
    if (threads && threads.length > 0) {
      router.replace(`/chat/projects/${params.pid}/threads/${threads[0].id}`);
    }
  }, [threads, params.pid, router]);

  return <div className="p-6 text-sm text-gray-500">Loading thread…</div>;
}
