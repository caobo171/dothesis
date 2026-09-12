"use client";

import {
  Listbox,
  ListboxButton,
  ListboxOption,
  ListboxOptions,
} from "@headlessui/react";
import { Check, ChevronDown } from "lucide-react";

import { cn } from "@/app/lib/utils";

export type SelectOption = {
  value: string;
  label: string;
};

type SelectProps = {
  id?: string;
  value: string;
  onValueChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  /** Match Input height in filter bars. */
  size?: "default" | "sm";
};

export function Select({
  id,
  value,
  onValueChange,
  options,
  placeholder = "Select…",
  disabled,
  className,
  size = "default",
}: SelectProps) {
  const selected = options.find((o) => o.value === value);

  return (
    <Listbox value={value} onChange={onValueChange} disabled={disabled}>
      <div className={cn("relative", className)}>
        <ListboxButton
          id={id}
          className={cn(
            "flex w-full items-center justify-between gap-2 rounded-lg border border-input bg-background px-3 text-left text-sm shadow-sm",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            "disabled:cursor-not-allowed disabled:opacity-50",
            size === "default" ? "h-10" : "h-9",
          )}
        >
          <span className={cn("min-w-0 truncate", !selected && "text-muted-foreground")}>
            {selected?.label ?? placeholder}
          </span>
          <ChevronDown className="size-4 shrink-0 text-ink-400" aria-hidden />
        </ListboxButton>

        <ListboxOptions
          anchor="bottom start"
          transition
          className={cn(
            "z-50 mt-1 max-h-60 w-[var(--button-width)] overflow-auto rounded-lg border border-ink-200 bg-white p-1 shadow-lg",
            "transition duration-100 ease-out data-[closed]:scale-95 data-[closed]:opacity-0",
          )}
        >
          {options.map((opt) => (
            <ListboxOption
              key={opt.value || "__all__"}
              value={opt.value}
              className={cn(
                "relative flex cursor-default select-none items-center rounded-md py-2 pl-8 pr-3 text-sm text-ink-900",
                "data-[focus]:bg-ink-50 data-[selected]:font-medium",
              )}
            >
              {({ selected: isSelected }) => (
                <>
                  <span
                    className={cn(
                      "absolute left-2 flex size-4 items-center justify-center text-primary-600",
                      isSelected ? "opacity-100" : "opacity-0",
                    )}
                  >
                    <Check className="size-4" aria-hidden />
                  </span>
                  {opt.label}
                </>
              )}
            </ListboxOption>
          ))}
        </ListboxOptions>
      </div>
    </Listbox>
  );
}
