"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { useListOpportunities } from "@/api/generated/default/default";
import type { OpportunityListItem } from "@/api/generated/model";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { PAGE_SIZE, Pagination } from "@/components/ui/pagination";
import { SearchInput } from "@/components/ui/search-input";
import { Skeleton } from "@/components/ui/skeleton";
import { relativeTime } from "@/lib/format";
import { AxisChip } from "@/components/opportunities/axis";

function matches(o: OpportunityListItem, q: string): boolean {
  const t = q.trim().toLowerCase();
  if (!t) return true;
  return [o.company_name, o.idea, o.sector, o.geo, o.status].some((v) =>
    v?.toLowerCase().includes(t),
  );
}

function Row({ o }: { o: OpportunityListItem }) {
  return (
    <Link href={`/opportunities/${o.id}`} className="block">
      <Card className="card-shadow-hover p-4 transition-all duration-200 active:scale-[0.995] sm:p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold text-foreground">
                {o.company_name ?? "Unnamed opportunity"}
              </span>
              <Badge variant="muted">{o.status}</Badge>
            </div>
            {o.idea && (
              <p className="mt-1 line-clamp-2 text-[13px] leading-relaxed text-muted-foreground">
                {o.idea}
              </p>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-subtle">
              {o.sector && <span>{o.sector}</span>}
              {o.geo && <span>{o.geo}</span>}
              <span>{relativeTime(o.created_at)}</span>
            </div>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-2">
            <div className="flex flex-wrap justify-end gap-1.5">
              {o.axes.map((a) => (
                <AxisChip key={a.axis} a={a} />
              ))}
              {o.axes.length === 0 && (
                <span className="text-[11px] text-subtle">not scored yet</span>
              )}
            </div>
            <ChevronRight className="h-4 w-4 text-subtle" />
          </div>
        </div>
      </Card>
    </Link>
  );
}

export function OpportunitiesList() {
  const { data, isLoading, isError } = useListOpportunities();
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);

  const rows = useMemo(() => (data ?? []).filter((o) => matches(o, query)), [data, query]);
  const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const visible = rows.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  if (isError) {
    return (
      <Card className="p-6 text-sm text-muted-foreground">
        Could not load opportunities. Is the backend running on{" "}
        <code className="text-foreground">localhost:8000</code>?
      </Card>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-28 w-full rounded-2xl" />
        ))}
      </div>
    );
  }

  return (
    <div>
      <SearchInput
        value={query}
        onChange={(v) => {
          setQuery(v);
          setPage(1);
        }}
        placeholder="Search company, idea, sector or geo"
        label="Search opportunities"
        className="mb-4"
      />
      <div className="space-y-3">
        {visible.map((o) => (
          <Row key={o.id} o={o} />
        ))}
        {rows.length === 0 && (
          <Card className="p-8 text-center text-sm text-muted-foreground">
            {data?.length
              ? "No opportunities match your search."
              : "No opportunities yet. Log one on the Inbound page to start the screening loop."}
          </Card>
        )}
      </div>
      <Pagination page={safePage} pageCount={pageCount} onPageChange={setPage} />
    </div>
  );
}
