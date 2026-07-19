"use client";

import { Search } from "lucide-react";

/** Rounded search field used by every list toolbar. */
export function SearchInput({
  value,
  onChange,
  placeholder,
  label = "Search",
  className = "",
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  label?: string;
  className?: string;
}) {
  return (
    <label className={`relative block ${className}`}>
      <span className="sr-only">{label}</span>
      <Search className="pointer-events-none absolute left-3.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-subtle" />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="h-8 w-full rounded-full bg-black/[0.04] pl-9 pr-4 text-xs text-foreground transition-colors placeholder:text-subtle hover:bg-black/[0.06] focus:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />
    </label>
  );
}
