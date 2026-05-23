"use client";

import useSWR from "swr";
import { swrFetcher } from "./api";
import type { Me } from "./types";

export function useMe() {
  return useSWR<Me>("/auth/me", swrFetcher);
}
