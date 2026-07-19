"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ChevronRight, Inbox, Paperclip } from "lucide-react";
import { useListFounders, useListOpportunities } from "@/api/generated/default/default";
import type { OpportunityListItem } from "@/api/generated/model";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { PAGE_SIZE, Pagination } from "@/components/ui/pagination";
import { SearchInput } from "@/components/ui/search-input";
import { Skeleton } from "@/components/ui/skeleton";
import { initials, relativeTime } from "@/lib/format";

function matches(o: OpportunityListItem, q: string): boolean {
  const t = q.trim().toLowerCase();
  if (!t) return true;
  return [o.company_name, o.idea, o.sector, o.geo, o.status].some((v) =>
    v?.toLowerCase().includes(t),
  );
}

function statusBadge(status: string): { variant: BadgeProps["variant"]; label: string } {
  if (status === "diligence") return { variant: "primary", label: "diligence" };
  if (status === "decided") return { variant: "success", label: "decided" };
  if (status === "rejected") return { variant: "danger", label: "rejected" };
  return { variant: "muted", label: "screening" };
}

/** One application, styled like an email: sender, subject, attachment, time, status. */
function InboxRow({ o, founderName }: { o: OpportunityListItem; founderName: string | null }) {
  const s = statusBadge(o.status);
  return (
    <Link
      href={`/opportunities/${o.id}`}
      className="flex items-start gap-3 px-4 py-3.5 transition-all duration-200 hover:bg-muted/60 active:scale-[0.995] sm:px-5"
    >
      <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold text-primary">
        {initials(o.company_name ?? o.sector ?? "?")}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-3">
          <span className="truncate text-sm font-semibold text-foreground">
            {o.company_name ?? "Unnamed applicant"}
            {founderName && (
              <span className="ml-2 font-normal text-muted-foreground">{founderName}</span>
            )}
          </span>
          <span className="shrink-0 text-xs tabular-nums text-subtle">
            {relativeTime(o.created_at)}
          </span>
        </div>
        <p className="mt-0.5 truncate text-[13px] text-muted-foreground">
          {o.idea ?? "No description yet"}
        </p>
        <div className="mt-1.5 flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5">
          <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-xs text-subtle">
            {o.source === "inbound" && (
              // Only genuine applications carry a deck (POST /apply requires the PDF).
              <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                <Paperclip className="h-3 w-3" />
                deck.pdf
              </span>
            )}
            {o.sector && <span>{o.sector}</span>}
            {o.geo && <span>{o.geo}</span>}
          </span>
          <span className="flex shrink-0 items-center gap-2">
            <Badge variant={s.variant}>{s.label}</Badge>
            <ChevronRight className="h-4 w-4 text-subtle" />
          </span>
        </div>
      </div>
    </Link>
  );
}

export function InboundView() {
  const { data, isLoading, isError } = useListOpportunities();
  const { data: founders } = useListFounders();
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);

  const founderNames = useMemo(
    () => new Map((founders ?? []).map((f) => [f.id, f.display_name])),
    [founders],
  );
  const rows = useMemo(() => (data ?? []).filter((o) => matches(o, query)), [data, query]);
  const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const visible = rows.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  if (isError) {
    return (
      <Card className="p-6 text-sm text-muted-foreground">
        Could not load applications. Is the backend running on{" "}
        <code className="text-foreground">localhost:8000</code>?
      </Card>
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
        placeholder="Search applications by company, idea, sector or geo"
        label="Search applications"
        className="mb-4"
      />
      <Card className="overflow-hidden">
        <div className="divide-y divide-border">
          {isLoading &&
            Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3 px-5 py-3.5">
                <Skeleton className="h-10 w-10 rounded-full" />
                <div className="flex-1 space-y-1.5">
                  <Skeleton className="h-3.5 w-48" />
                  <Skeleton className="h-3 w-72" />
                </div>
              </div>
            ))}
          {!isLoading &&
            visible.map((o) => (
              <InboxRow key={o.id} o={o} founderName={founderNames.get(o.founder_id ?? "") ?? null} />
            ))}
          {!isLoading && rows.length === 0 && (
            <div className="flex flex-col items-center gap-2 px-5 py-12 text-center">
              <Inbox className="h-6 w-6 text-subtle" />
              <p className="text-sm text-muted-foreground">
                {data?.length ? "No applications match your search." : "Inbox zero."}
              </p>
            </div>
          )}
        </div>
      </Card>
      <Pagination page={safePage} pageCount={pageCount} onPageChange={setPage} />
    </div>
  );
}
