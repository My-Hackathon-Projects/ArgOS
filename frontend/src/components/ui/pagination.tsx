"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

/** Compact pager: prev/next chevrons around a page indicator. Hidden when one page. */
export function Pagination({
  page,
  pageCount,
  onPageChange,
}: {
  page: number;
  pageCount: number;
  onPageChange: (page: number) => void;
}) {
  if (pageCount <= 1) return null;

  const btn =
    "flex h-8 w-8 items-center justify-center rounded-full transition-all duration-200 active:scale-[0.94] disabled:pointer-events-none disabled:opacity-35 hover:bg-black/[0.05]";

  return (
    <nav aria-label="Pagination" className="mt-5 flex items-center justify-center gap-3">
      <button
        type="button"
        className={cn(btn)}
        onClick={() => onPageChange(page - 1)}
        disabled={page <= 1}
        aria-label="Previous page"
      >
        <ChevronLeft className="h-4 w-4" />
      </button>
      <span className="text-xs tabular-nums text-muted-foreground">
        Page <span className="font-medium text-foreground">{page}</span> of {pageCount}
      </span>
      <button
        type="button"
        className={cn(btn)}
        onClick={() => onPageChange(page + 1)}
        disabled={page >= pageCount}
        aria-label="Next page"
      >
        <ChevronRight className="h-4 w-4" />
      </button>
    </nav>
  );
}

export const PAGE_SIZE = 10;
