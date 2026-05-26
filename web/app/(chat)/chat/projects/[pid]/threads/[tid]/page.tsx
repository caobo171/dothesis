"use client";

import { useParams } from "next/navigation";
import { ChatPane } from "@/app/components/chat/ChatPane";


export default function ThreadPage() {
  const params = useParams<{ pid: string; tid: string }>();
  return <ChatPane projectId={params.pid} threadId={params.tid} />;
}
