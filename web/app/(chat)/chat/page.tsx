import { redirect } from "next/navigation";

// 2026-06-10 — the home dashboard moved to the root route (the page users
// actually land on). /chat stays as a redirect so old links and the legacy
// "Start New Draft" button keep working; the chat workspace itself lives at
// /chat/projects/[pid].
export default function ChatHome() {
  redirect("/");
}
