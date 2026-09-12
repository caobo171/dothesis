"use client";

import { Label } from "@/app/components/ui/label";
import { Select, type SelectOption } from "@/app/components/ui/select";
import { cn } from "@/app/lib/utils";

type FilterSelectProps = {
  label: string;
  id: string;
  value: string;
  onValueChange: (value: string) => void;
  options: SelectOption[];
  className?: string;
};

/** Labelled select for admin list filter bars (Papers, Jobs, Orders, …). */
export function FilterSelect({
  label,
  id,
  value,
  onValueChange,
  options,
  className,
}: FilterSelectProps) {
  return (
    <div className={cn("w-full shrink-0 space-y-2", className)}>
      <Label htmlFor={id}>{label}</Label>
      <Select id={id} value={value} onValueChange={onValueChange} options={options} />
    </div>
  );
}
