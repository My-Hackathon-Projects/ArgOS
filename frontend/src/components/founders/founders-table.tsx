"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { useListFounders } from "@/api/generated/default/default";
import type { FounderListItem } from "@/api/generated/model";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { initials } from "@/lib/format";

function statusBadge(status: string): { variant: BadgeProps["variant"]; label: string } {
  if (status === "confirmed") return { variant: "success", label: "Confirmed" };
  if (status === "needs_review") return { variant: "danger", label: "Needs review" };
  return { variant: "muted", label: "Candidate" };
}

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

function Row({ f }: { f: FounderListItem }) {
  const s = statusBadge(f.status);
  return (
    <Link
      href={`/founders/${f.id}`}
      className="group grid grid-cols-[1.6fr_1.1fr_0.8fr_auto_auto_auto] items-center gap-4 px-5 py-3.5 transition-colors hover:bg-muted/60"
    >
      <div className="flex min-w-0 items-center gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold text-muted-foreground">
          {initials(f.display_name)}
        </span>
        <div className="min-w-0">
          <div className="truncate text-sm font-medium text-foreground">
            {f.display_name ?? "Unknown"}
          </div>
          {f.occupation && (
            <div className="truncate text-xs text-muted-foreground">{f.occupation}</div>
          )}
        </div>
      </div>
      <div className="truncate text-sm text-muted-foreground">{f.current_company ?? "—"}</div>
      <div className="truncate text-sm text-muted-foreground">{f.city ?? "—"}</div>
      <div className="text-sm tabular-nums text-muted-foreground">
        {f.signal_count}
        <span className="ml-1 text-xs text-subtle">signals</span>
      </div>
      <Confidence value={f.discovery_confidence} />
      <div className="flex items-center gap-3">
        <Badge variant={s.variant}>{s.label}</Badge>
        <ChevronRight className="h-4 w-4 text-subtle transition-transform group-hover:translate-x-0.5" />
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
      <div className="grid grid-cols-[1.6fr_1.1fr_0.8fr_auto_auto_auto] gap-4 border-b border-border bg-surface-muted px-5 py-2.5 text-[11px] font-medium uppercase tracking-wider text-subtle">
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
      </div>
    </Card>
  );
}
