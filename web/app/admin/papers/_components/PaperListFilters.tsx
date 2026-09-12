"use client";

import { Search } from "lucide-react";

import { FilterSelect } from "@/app/components/admin/FilterSelect";
import { Button } from "@/app/components/ui/button";
import { Input } from "@/app/components/ui/input";
import { Label } from "@/app/components/ui/label";

const FILTER_ALL = "";

const MODULES = ["", "M1", "M2", "M3", "M4", "M5"];
const STATUSES = ["", "draft", "running", "done", "failed", "canceled"];

type PaperListFiltersProps = {
  searchParams: Pick<URLSearchParams, "get">;
  onFilterChange: (key: string, value: string) => void;
};

function readInput(id: string): string {
  return (document.getElementById(id) as HTMLInputElement | null)?.value ?? "";
}

export function PaperListFilters({ searchParams, onFilterChange }: PaperListFiltersProps) {
  const moduleValue = searchParams.get("module") ?? FILTER_ALL;
  const statusValue = searchParams.get("status") ?? FILTER_ALL;

  return (
    <div className="mb-3 flex flex-wrap items-end gap-3">
      <div className="w-full shrink-0 space-y-2 sm:w-72">
        <Label htmlFor="papers-admin-search">Topic</Label>
        <div className="flex min-w-0 items-center gap-2">
          <Input
            id="papers-admin-search"
            placeholder="Search topic or field…"
            defaultValue={searchParams.get("q") || ""}
            className="min-w-0 flex-1"
            onKeyDown={(e) => {
              if (e.key === "Enter") onFilterChange("q", readInput("papers-admin-search"));
            }}
          />
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="shrink-0"
            aria-label="Apply topic search"
            onClick={() => onFilterChange("q", readInput("papers-admin-search"))}
          >
            <Search className="size-4" />
          </Button>
        </div>
      </div>

      <div className="w-full shrink-0 space-y-2 sm:w-64">
        <Label htmlFor="papers-admin-owner">Owner</Label>
        <div className="flex min-w-0 items-center gap-2">
          <Input
            id="papers-admin-owner"
            placeholder="Filter by owner email"
            defaultValue={searchParams.get("owner") || ""}
            className="min-w-0 flex-1"
            onKeyDown={(e) => {
              if (e.key === "Enter") onFilterChange("owner", readInput("papers-admin-owner"));
            }}
          />
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="shrink-0"
            aria-label="Apply owner filter"
            onClick={() => onFilterChange("owner", readInput("papers-admin-owner"))}
          >
            <Search className="size-4" />
          </Button>
        </div>
      </div>

      <FilterSelect
        id="papers-admin-module"
        label="Module"
        className="sm:w-40"
        value={moduleValue}
        onValueChange={(v) => onFilterChange("module", v)}
        options={MODULES.map((m) => ({ value: m, label: m || "All modules" }))}
      />

      <FilterSelect
        id="papers-admin-status"
        label="Status"
        className="sm:w-40"
        value={statusValue}
        onValueChange={(v) => onFilterChange("status", v)}
        options={STATUSES.map((s) => ({ value: s, label: s || "All status" }))}
      />
    </div>
  );
}
