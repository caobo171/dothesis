"use client";

import { useEffect } from "react";
import useSWR from "swr";
import { useParams, useRouter } from "next/navigation";
import { swrFetcher as fetcher } from "@/app/lib/api";
import { useT } from "@/app/lib/i18n/LocaleProvider";


export default function ProjectIndex() {
  const router = useRouter();
  const params = useParams<{ pid: string }>();
  const t = useT();
  const { data: threads, error } = useSWR<Array<{ id: string }>>(
    `/projects/${params.pid}/threads/list`, fetcher,
  );

  useEffect(() => {
    if (threads && threads.length > 0) {
      router.replace(`/chat/projects/${params.pid}/threads/${threads[0].id}`);
    }
  }, [threads, params.pid, router]);

  // "Loading thread…" used to be the only thing this route could ever render:
  // a failed fetch and a project with zero threads both left `threads` falsy,
  // so the redirect never fired and the spinner text never changed.
  if (error) {
    return (
      <div className="p-6 text-sm text-[#6E5121]">
        {t("ws.projectThreadsFailed")}{" "}
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="underline font-semibold hover:no-underline"
        >
          {t("ws.retry")}
        </button>
      </div>
    );
  }

  if (threads && threads.length === 0) {
    return (
      <div className="p-6 text-sm text-ink-500">
        {t("ws.threadsEmpty")}
      </div>
    );
  }

  return <div className="p-6 text-sm text-ink-500">{t("ws.loadingThread")}</div>;
}
