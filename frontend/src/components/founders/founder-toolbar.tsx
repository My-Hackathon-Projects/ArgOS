"use client";

import { ChevronDown, Search } from "lucide-react";
import { FilterPills, type FilterOption } from "@/components/ui/filter-pills";

/** Founders toolbar: search field, status segmented control, city dropdown. */
export function FounderToolbar({
  query,
  onQuery,
  statusOptions,
  cityOptions,
  status,
  city,
  onStatus,
  onCity,
}: {
  query: string;
  onQuery: (v: string) => void;
  statusOptions: FilterOption[];
  cityOptions: FilterOption[];
  status: string | null;
  city: string | null;
  onStatus: (v: string | null) => void;
  onCity: (v: string | null) => void;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      <label className="relative min-w-[220px] flex-1">
        <span className="sr-only">Search founders</span>
        <Search className="pointer-events-none absolute left-3.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-subtle" />
        <input
          type="search"
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          placeholder="Search name, company, role or city"
          className="h-8 w-full rounded-full bg-black/[0.04] pl-9 pr-4 text-xs text-foreground transition-colors placeholder:text-subtle hover:bg-black/[0.06] focus:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </label>
      <FilterPills
        layoutId="founder-status-pill"
        options={statusOptions}
        selected={status}
        onSelect={onStatus}
      />
      {cityOptions.length > 1 && (
        <label className="relative">
          <span className="sr-only">Filter by city</span>
          <select
            value={city ?? ""}
            onChange={(e) => onCity(e.target.value || null)}
            className="cursor-pointer appearance-none rounded-full bg-black/[0.04] py-1.5 pl-3.5 pr-8 text-xs font-medium text-foreground transition-colors hover:bg-black/[0.07] focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <option value="">All cities</option>
            {cityOptions.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-subtle" />
        </label>
      )}
    </div>
  );
}
