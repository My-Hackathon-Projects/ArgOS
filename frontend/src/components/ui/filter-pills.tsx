"use client";

import { motion } from "motion/react";
import { cn } from "@/lib/utils";

export type FilterOption = { value: string; label: string };

/** One pill group with an animated highlight. `layoutId` must be unique per group. */
export function FilterPills({
  options,
  selected,
  onSelect,
  layoutId,
  allLabel = "All",
}: {
  options: FilterOption[];
  selected: string | null;
  onSelect: (value: string | null) => void;
  layoutId: string;
  allLabel?: string;
}) {
  if (options.length <= 1) return null;

  const items: FilterOption[] = [{ value: "", label: allLabel }, ...options];

  return (
    <div className="flex gap-1 rounded-full bg-black/[0.04] p-1">
      {items.map(({ value, label }) => {
        const active = (value || null) === selected;
        return (
          <button
            key={value || "all"}
            type="button"
            onClick={() => onSelect(value || null)}
            className={cn(
              "relative whitespace-nowrap rounded-full px-3.5 py-1 text-xs transition-colors duration-200",
              active ? "font-medium text-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {active && (
              <motion.span
                layoutId={layoutId}
                className="card-shadow absolute inset-0 rounded-full bg-surface"
                transition={{ type: "spring", bounce: 0.18, duration: 0.5 }}
              />
            )}
            <span className="relative">{label}</span>
          </button>
        );
      })}
    </div>
  );
}
