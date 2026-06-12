"use client";

import useSWR from "swr";
import { apiFetch } from "./api";
import type { Me } from "./types";

// /auth/me is POST-only (CLAUDE.md). useSWR's default fetcher does GET,
// which 405s — wrap apiFetch with an explicit POST method so the access
// token rides in the JSON body the way the new dependency expects.
export function useMe() {
  return useSWR<Me>("/auth/me", (url: string) => apiFetch(url, { method: "POST" }));
}
