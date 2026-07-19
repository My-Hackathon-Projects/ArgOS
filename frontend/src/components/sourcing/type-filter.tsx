"use client";

import { ListFilter } from "lucide-react";
import { FilterPills } from "@/components/ui/filter-pills";
import { humanize } from "@/lib/source-style";

/** Signal-type filter chips (scrolls horizontally on small screens). */
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
