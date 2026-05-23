"use client";

import useSWR from "swr";
import { Dashboard } from "../components/dashboard";
import { swrFetcher } from "../lib/api";

export default function Page() {
  const { data: papers, error, isLoading, mutate } = useSWR("/papers", swrFetcher);
  return <Dashboard papers={papers || []} loading={isLoading} error={error} refresh={mutate} />;
}
