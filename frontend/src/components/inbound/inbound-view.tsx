"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ChevronRight, FileUp, Inbox, Plus } from "lucide-react";
import { useListOpportunities } from "@/api/generated/default/default";
import type { OpportunityListItem } from "@/api/generated/model";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PAGE_SIZE, Pagination } from "@/components/ui/pagination";
import { SearchInput } from "@/components/ui/search-input";
import { Skeleton } from "@/components/ui/skeleton";
import { initials, relativeTime } from "@/lib/format";
import { ApplicationForm } from "@/components/inbound/application-form";
import { DeckApply } from "@/components/inbound/deck-apply";

function matches(o: OpportunityListItem, q: string): boolean {
  const t = q.trim().toLowerCase();
  if (!t) return true;
  return [o.company_name, o.idea, o.sector, o.geo, o.status].some((v) =>
    v?.toLowerCase().includes(t),
  );
}

/** One application, styled like an inbox row: sender, subject, preview, time. */
function InboxRow({ o }: { o: OpportunityListItem }) {
  return (
    <Link
      href={`/opportunities/${o.id}`}
      className="flex items-center gap-3 px-4 py-3.5 transition-all duration-200 hover:bg-muted/60 active:scale-[0.995] sm:px-5"
    >
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold text-primary">
        {initials(o.company_name ?? o.sector ?? "?")}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-3">
          <span className="truncate text-sm font-semibold text-foreground">
            {o.company_name ?? "Unnamed applicant"}
          </span>
          <span className="shrink-0 text-xs tabular-nums text-subtle">
            {relativeTime(o.created_at)}
          </span>
        </div>
        <div className="mt-0.5 flex items-center justify-between gap-3">
          <span className="truncate text-[13px] text-muted-foreground">
            {o.idea ?? o.sector ?? "No description yet"}
          </span>
          <span className="flex shrink-0 items-center gap-2">
            <Badge variant="muted">{o.status}</Badge>
            <ChevronRight className="h-4 w-4 text-subtle" />
          </span>
        </div>
      </div>
    </Link>
  );
}

export function InboundView() {
  const { data, isLoading, isError } = useListOpportunities();
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [panel, setPanel] = useState<"deck" | "manual" | null>(null);

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
      <div className="mb-4">
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant={panel === "deck" ? "secondary" : "primary"}
            onClick={() => setPanel(panel === "deck" ? null : "deck")}
          >
            <FileUp className="h-4 w-4" />
            {panel === "deck" ? "Close" : "Apply with deck"}
          </Button>
          <Button
            size="sm"
            variant={panel === "manual" ? "secondary" : "outline"}
            onClick={() => setPanel(panel === "manual" ? null : "manual")}
          >
            <Plus className="h-4 w-4" />
            {panel === "manual" ? "Close" : "Log by hand"}
          </Button>
        </div>
        <DeckApply open={panel === "deck"} onClose={() => setPanel(null)} />
        <ApplicationForm open={panel === "manual"} onClose={() => setPanel(null)} />
      </div>
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
            Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3 px-5 py-3.5">
                <Skeleton className="h-9 w-9 rounded-full" />
                <div className="flex-1 space-y-1.5">
                  <Skeleton className="h-3.5 w-48" />
                  <Skeleton className="h-3 w-72" />
                </div>
              </div>
            ))}
          {!isLoading && visible.map((o) => <InboxRow key={o.id} o={o} />)}
          {!isLoading && rows.length === 0 && (
            <div className="flex flex-col items-center gap-2 px-5 py-12 text-center">
              <Inbox className="h-6 w-6 text-subtle" />
              <p className="text-sm text-muted-foreground">
                {data?.length
                  ? "No applications match your search."
                  : "Inbox zero. Log the first application above."}
              </p>
            </div>
          )}
        </div>
      </Card>
      <Pagination page={safePage} pageCount={pageCount} onPageChange={setPage} />
    </div>
  );
}
