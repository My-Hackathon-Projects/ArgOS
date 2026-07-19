"use client";

import { ChevronDown, ListFilter } from "lucide-react";
import { FilterPills } from "@/components/ui/filter-pills";
import { humanize } from "@/lib/source-style";

// Above this many distinct types the pill row becomes unusable; switch to a dropdown.
const MAX_PILLS = 6;

/** Signal-type filter: pills for a handful of types, a compact dropdown for many. */
export function TypeFilter({
  types,
  selected,
  onSelect,
}: {
  types: string[];
  selected: string | null;
  onSelect: (type: string | null) => void;
}) {
  if (types.length <= 1) return null;

  if (types.length > MAX_PILLS) {
    return (
      <div className="mb-3 flex items-center gap-2">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-black/[0.04] text-muted-foreground">
          <ListFilter className="h-3.5 w-3.5" aria-hidden />
        </span>
        <label className="relative">
          <span className="sr-only">Filter by signal type</span>
          <select
            value={selected ?? ""}
            onChange={(e) => onSelect(e.target.value || null)}
            className="cursor-pointer appearance-none rounded-full bg-black/[0.04] py-1.5 pl-3.5 pr-8 text-xs font-medium text-foreground transition-colors hover:bg-black/[0.07] focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <option value="">All types ({types.length})</option>
            {types.map((t) => (
              <option key={t} value={t}>
                {humanize(t)}
              </option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-subtle" />
        </label>
      </div>
    );
  }

  return (
    <div className="-mx-4 mb-3 overflow-x-auto px-4 sm:mx-0 sm:px-0">
      <div className="flex w-max items-center gap-2">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-black/[0.04] text-muted-foreground">
          <ListFilter className="h-3.5 w-3.5" aria-hidden />
        </span>
        <FilterPills
          layoutId="signal-type-pill"
          options={types.map((t) => ({ value: t, label: humanize(t) }))}
          selected={selected}
          onSelect={onSelect}
        />
      </div>
    </div>
  );
}
