"use client";

import useSWR from "swr";
import { Sidebar } from "./components/shared";
import { Dashboard } from "./components/dashboard";
import { swrFetcher } from "./lib/api";

export default function Page() {
  const { data: papers, error, isLoading, mutate } = useSWR("/papers", swrFetcher);

  return (
    <div className="app">
      <Sidebar />
      <Dashboard papers={papers || []} loading={isLoading} error={error} refresh={mutate} />
    </div>
  );
}
