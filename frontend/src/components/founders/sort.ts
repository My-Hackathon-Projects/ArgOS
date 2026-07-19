import type { FounderListItem } from "@/api/generated/model";

export type SortKey = "name" | "company" | "city" | "signals" | "confidence";
export type SortState = { key: SortKey; dir: "asc" | "desc" } | null;

const getters: Record<SortKey, (f: FounderListItem) => string | number | null> = {
  name: (f) => f.display_name,
  company: (f) => f.current_company,
  city: (f) => f.city,
  signals: (f) => f.signal_count,
  confidence: (f) => f.discovery_confidence,
};

/** Stable client-side sort; null values always sink to the bottom. */
export function sortFounders(rows: FounderListItem[], sort: SortState): FounderListItem[] {
  if (!sort) return rows;
  const get = getters[sort.key];
  const mul = sort.dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const va = get(a);
    const vb = get(b);
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    if (typeof va === "number" && typeof vb === "number") return (va - vb) * mul;
    return String(va).localeCompare(String(vb)) * mul;
  });
}

/** Case-insensitive match across the searchable founder fields. */
export function matchesQuery(f: FounderListItem, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return [f.display_name, f.current_company, f.occupation, f.city].some((v) =>
    v?.toLowerCase().includes(q),
  );
}
