"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { useListFounders } from "@/api/generated/default/default";
import type { FounderListItem } from "@/api/generated/model";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { initials } from "@/lib/format";
import { statusBadge } from "@/components/founders/status";

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

const GRID = "md:grid-cols-[1.6fr_1.1fr_0.8fr_auto_auto_auto]";

function Row({ f }: { f: FounderListItem }) {
  const s = statusBadge(f.status);
  return (
    <Link
      href={`/founders/${f.id}`}
      className={`group block px-4 py-3.5 transition-colors hover:bg-muted/60 sm:px-5 md:grid md:items-center md:gap-4 ${GRID}`}
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
      <div className="hidden md:block">
        <Confidence value={f.discovery_confidence} />
      </div>
      <div className="hidden items-center gap-3 md:flex">
        <Badge variant={s.variant}>{s.label}</Badge>
        <ChevronRight className="h-4 w-4 text-subtle transition-transform group-hover:translate-x-0.5" />
      </div>

      {/* Mobile summary line */}
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 pl-12 text-xs text-muted-foreground md:hidden">
        {f.current_company && <span className="truncate">{f.current_company}</span>}
        {f.city && <span>{f.city}</span>}
        <span className="tabular-nums">{f.signal_count} signals</span>
        <Confidence value={f.discovery_confidence} />
      </div>
    </Link>
  );
}

export function FoundersTable() {
  const { data, isLoading, isError } = useListFounders();

  if (isError) {
    return (
      <Card className="p-6 text-sm text-muted-foreground">
        Could not load founders. Is the backend running on{" "}
        <code className="text-foreground">localhost:8000</code>?
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden">
      <div
        className={`hidden border-b border-border bg-surface-muted px-5 py-2.5 text-[11px] font-medium uppercase tracking-wider text-subtle md:grid md:gap-4 ${GRID}`}
      >
        <span>Founder</span>
        <span>Company</span>
        <span>Location</span>
        <span>Signals</span>
        <span>Confidence</span>
        <span>Status</span>
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
          : data?.map((f) => <Row key={f.id} f={f} />)}
        {!isLoading && data?.length === 0 && (
          <div className="px-5 py-10 text-center text-sm text-muted-foreground">
            No founders yet. Run discovery on the Sourcing page to start resolving people.
          </div>
        )}
      </div>
    </Card>
  );
}
