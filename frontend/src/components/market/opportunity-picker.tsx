"use client";

import { motion } from "motion/react";
import type { MarketOpportunityListItem } from "@/api/generated/model";
import { cn } from "@/lib/utils";

/** Horizontal pill selector for analysed opportunities (scrolls on small screens). */
export function OpportunityPicker({
  items,
  selectedId,
  onSelect,
}: {
  items: MarketOpportunityListItem[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (items.length <= 1) return null;

  return (
    <div className="-mx-4 mb-5 overflow-x-auto px-4 sm:mx-0 sm:px-0">
      <div className="flex w-max gap-1 rounded-full bg-black/[0.04] p-1">
        {items.map((o) => {
          const active = o.id === selectedId;
          return (
            <button
              key={o.id}
              type="button"
              onClick={() => onSelect(o.id)}
              className={cn(
                "relative whitespace-nowrap rounded-full px-4 py-1.5 text-xs transition-colors duration-200",
                active ? "font-medium text-foreground" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {active && (
                <motion.span
                  layoutId="opportunity-pill"
                  className="card-shadow absolute inset-0 rounded-full bg-surface"
                  transition={{ type: "spring", bounce: 0.18, duration: 0.5 }}
                />
              )}
              <span className="relative">{o.company_name ?? o.sector ?? "Opportunity"}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
