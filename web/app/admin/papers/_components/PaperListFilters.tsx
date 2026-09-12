"use client";

import { Search } from "lucide-react";

import { FilterSelect } from "@/app/components/admin/FilterSelect";
import { Button } from "@/app/components/ui/button";
import { Input } from "@/app/components/ui/input";
import { Label } from "@/app/components/ui/label";
import { useT } from "@/app/lib/i18n/LocaleProvider";

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
  const t = useT();
  const moduleValue = searchParams.get("module") ?? FILTER_ALL;
  const statusValue = searchParams.get("status") ?? FILTER_ALL;

  return (
    <div className="mb-3 flex flex-wrap items-end gap-3">
      <div className="w-full shrink-0 space-y-2 sm:w-72">
        <Label htmlFor="papers-admin-search">{t("admin.filters.topic")}</Label>
        <div className="flex min-w-0 items-center gap-2">
          <Input
            id="papers-admin-search"
            placeholder={t("admin.filters.searchTopic")}
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
        <Label htmlFor="papers-admin-owner">{t("admin.filters.owner")}</Label>
        <div className="flex min-w-0 items-center gap-2">
          <Input
            id="papers-admin-owner"
            placeholder={t("admin.filters.searchOwner")}
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
        label={t("admin.filters.module")}
        className="sm:w-40"
        value={moduleValue}
        onValueChange={(v) => onFilterChange("module", v)}
        options={MODULES.map((m) => ({ value: m, label: m || t("admin.filters.allModules") }))}
      />

      <FilterSelect
        id="papers-admin-status"
        label={t("admin.filters.status")}
        className="sm:w-40"
        value={statusValue}
        onValueChange={(v) => onFilterChange("status", v)}
        options={STATUSES.map((s) => ({ value: s, label: s || t("admin.filters.allStatus") }))}
      />
    </div>
  );
}
