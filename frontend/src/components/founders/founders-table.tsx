"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowDown, ArrowUp, ChevronRight, ChevronsUpDown } from "lucide-react";
import { useListFounders } from "@/api/generated/default/default";
import type { FounderListItem } from "@/api/generated/model";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { PAGE_SIZE, Pagination } from "@/components/ui/pagination";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { initials } from "@/lib/format";
import { FounderToolbar } from "@/components/founders/founder-toolbar";
import { matchesQuery, sortFounders, type SortKey, type SortState } from "@/components/founders/sort";
import { statusBadge } from "@/components/founders/status";

// One shared template for the header row and every body row. The trailing columns are
// fixed widths so all grids resolve identically and the headings line up with the cells.
const GRID =
  "md:grid-cols-[minmax(0,1.8fr)_minmax(0,1.1fr)_minmax(0,0.85fr)_5.5rem_5rem_8rem_8rem]";

function Confidence({ value }: { value: number | null }) {
  if (value == null) return <span className="text-xs text-subtle">—</span>;
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-14 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs tabular-nums text-muted-foreground">{pct}%</span>
    </div>
  );
}

function SortHeader({
  label,
  k,
  sort,
  onSort,
}: {
  label: string;
  k: SortKey;
  sort: SortState;
  onSort: (k: SortKey) => void;
}) {
  const active = sort?.key === k;
  const Icon = active ? (sort.dir === "asc" ? ArrowUp : ArrowDown) : ChevronsUpDown;
  return (
    <button
      type="button"
      onClick={() => onSort(k)}
      className={cn(
        "group flex items-center gap-1 uppercase tracking-wider transition-colors hover:text-foreground",
        active ? "text-foreground" : "",
      )}
      aria-label={`Sort by ${label}`}
    >
      {label}
      <Icon
        className={cn(
          "h-3 w-3 shrink-0",
          active ? "text-foreground" : "text-border-strong group-hover:text-subtle",
        )}
      />
    </button>
  );
}

function Row({ f }: { f: FounderListItem }) {
  const s = statusBadge(f.status);
  return (
    <Link
      href={`/founders/${f.id}`}
      className={`group block px-4 py-3.5 transition-all duration-200 hover:bg-muted/60 active:scale-[0.995] active:bg-muted sm:px-5 md:grid md:items-center md:gap-4 ${GRID}`}
    >
      {/* Identity cell (always visible) */}
      <div className="flex min-w-0 items-center gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold text-muted-foreground">
          {initials(f.display_name)}
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium text-foreground">
            {f.display_name ?? "Unknown"}
          </div>
          {f.occupation && (
            <div className="truncate text-xs text-muted-foreground">{f.occupation}</div>
          )}
        </div>
        <span className="flex items-center gap-2 md:hidden">
          <Badge variant={s.variant}>{s.label}</Badge>
          <ChevronRight className="h-4 w-4 text-subtle" />
        </span>
      </div>

      {/* Desktop columns */}
      <div className="hidden truncate text-sm text-muted-foreground md:block">
        {f.current_company ?? "—"}
      </div>
      <div className="hidden truncate text-sm text-muted-foreground md:block">{f.city ?? "—"}</div>
      <div className="hidden text-sm tabular-nums text-muted-foreground md:block">
        {f.signal_count}
        <span className="ml-1 text-xs text-subtle">signals</span>
      </div>
      <div
        className="hidden text-sm font-semibold tabular-nums md:block"
        style={{ color: f.founder_score != null ? "var(--axis-founder)" : undefined }}
      >
        {f.founder_score != null ? Math.round(f.founder_score) : <span className="font-normal text-subtle">—</span>}
      </div>
      <div className="hidden md:block">
        <Confidence value={f.discovery_confidence} />
      </div>
      <div className="hidden items-center justify-between gap-2 md:flex">
        <Badge variant={s.variant}>{s.label}</Badge>
        <ChevronRight className="h-4 w-4 shrink-0 text-subtle transition-transform group-hover:translate-x-0.5" />
      </div>

      {/* Mobile summary line */}
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 pl-12 text-xs text-muted-foreground md:hidden">
        {f.current_company && <span className="truncate">{f.current_company}</span>}
        {f.city && <span>{f.city}</span>}
        <span className="tabular-nums">{f.signal_count} signals</span>
        {f.founder_score != null && (
          <span
            className="font-semibold tabular-nums"
            style={{ color: "var(--axis-founder)" }}
          >
            score {Math.round(f.founder_score)}
          </span>
        )}
        <Confidence value={f.discovery_confidence} />
      </div>
    </Link>
  );
}

export function FoundersTable() {
  const { data, isLoading, isError } = useListFounders();
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [city, setCity] = useState<string | null>(null);
  const [sort, setSort] = useState<SortState>(null);

  const statusOptions = useMemo(
    () =>
      [...new Set((data ?? []).map((f) => f.status))]
        .sort()
        .map((s) => ({ value: s, label: statusBadge(s).label })),
    [data],
  );
  const cityOptions = useMemo(
    () =>
      [...new Set((data ?? []).map((f) => f.city).filter((c): c is string => !!c))]
        .sort()
        .map((c) => ({ value: c, label: c })),
    [data],
  );
  const rows = useMemo(() => {
    const filtered = (data ?? []).filter(
      (f) =>
        (!status || f.status === status) &&
        (!city || f.city === city) &&
        matchesQuery(f, query),
    );
    return sortFounders(filtered, sort);
  }, [data, status, city, query, sort]);

  const onSort = (k: SortKey) => {
    setSort((prev) =>
      prev?.key === k ? { key: k, dir: prev.dir === "asc" ? "desc" : "asc" } : { key: k, dir: "asc" },
    );
    setPage(1);
  };

  if (isError) {
    return (
      <Card className="p-6 text-sm text-muted-foreground">
        Could not load founders. Is the backend running on{" "}
        <code className="text-foreground">localhost:8000</code>?
      </Card>
    );
  }

  const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const visible = rows.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  return (
    <>
      <FounderToolbar
        query={query}
        onQuery={(v) => {
          setQuery(v);
          setPage(1);
        }}
        statusOptions={statusOptions}
        cityOptions={cityOptions}
        status={status}
        city={city}
        onStatus={(v) => {
          setStatus(v);
          setPage(1);
        }}
        onCity={(v) => {
          setCity(v);
          setPage(1);
        }}
      />
      <Card className="overflow-hidden">
        <div
          className={`hidden border-b border-border bg-surface-muted px-5 py-2.5 text-[11px] font-medium text-subtle md:grid md:items-center md:gap-4 ${GRID}`}
        >
          <SortHeader label="Founder" k="name" sort={sort} onSort={onSort} />
          <SortHeader label="Company" k="company" sort={sort} onSort={onSort} />
          <SortHeader label="Location" k="city" sort={sort} onSort={onSort} />
          <SortHeader label="Signals" k="signals" sort={sort} onSort={onSort} />
          <SortHeader label="Score" k="score" sort={sort} onSort={onSort} />
          <SortHeader label="Confidence" k="confidence" sort={sort} onSort={onSort} />
          <span className="uppercase tracking-wider">Status</span>
        </div>
        <div className="divide-y divide-border">
          {isLoading
            ? Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="flex items-center gap-3 px-5 py-3.5">
                  <Skeleton className="h-9 w-9 rounded-full" />
                  <div className="flex-1 space-y-1.5">
                    <Skeleton className="h-3.5 w-40" />
                    <Skeleton className="h-3 w-24" />
                  </div>
                </div>
              ))
            : visible.map((f) => <Row key={f.id} f={f} />)}
          {!isLoading && data?.length === 0 && (
            <div className="px-5 py-10 text-center text-sm text-muted-foreground">
              No founders yet. Run discovery on the Sourcing page to start resolving people.
            </div>
          )}
          {!isLoading && (data?.length ?? 0) > 0 && rows.length === 0 && (
            <div className="px-5 py-10 text-center text-sm text-muted-foreground">
              No founders match your search or filters.
            </div>
          )}
        </div>
      </Card>
      <Pagination page={safePage} pageCount={pageCount} onPageChange={setPage} />
    </>
  );
}
