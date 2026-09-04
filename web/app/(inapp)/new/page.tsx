"use client";

// /new used to hold the whole start flow. That flow now lives on the homepage
// (HomeLauncher), so there is ONE start surface. This route stays only as a
// redirect: existing links ("New thesis", the sidebar, bookmarks) keep working
// and land on the launcher instead of a second, duplicate start screen.
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function NewThesisRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/");
  }, [router]);
  return null;
}
