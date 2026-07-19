"use client";

import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Loader2, Scale, Timer, User } from "lucide-react";
import { useDecide, useGetOpportunity, useScreen } from "@/api/generated/default/default";
import type { OpportunityDetail as OpportunityDetailType } from "@/api/generated/model";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { duration, relativeTime } from "@/lib/format";
import { AXIS_ORDER, AxisScoreCard } from "@/components/opportunities/axis";
import { MarketAnalysis } from "@/components/market/market-analysis";
import { MemoSection } from "@/components/opportunities/memo-section";

const DECISIONS = [
  { key: "pursue", label: "Pursue" },
  { key: "track", label: "Track" },
  { key: "pass", label: "Pass" },
] as const;

function DecisionBar({ o }: { o: OpportunityDetailType }) {
  const qc = useQueryClient();
  const decide = useDecide({ mutation: { onSuccess: () => qc.invalidateQueries() } });
  const { id: opportunityId, decision } = o;
  return (
    <Card className="mt-6 flex flex-wrap items-center justify-between gap-3 p-5">
      <div>
        <h2 className="text-sm font-semibold text-foreground">Decision</h2>
        <p className="mt-0.5 text-xs text-subtle">
          {decision
            ? `Decided ${relativeTime(o.decided_at)} — you can revise it.`
            : "Record the call — completes the funnel and stamps signal→decision latency."}
        </p>
        {decision && o.signal_to_decision_seconds != null && (
          <p className="mt-1 inline-flex items-center gap-1.5 text-xs text-subtle">
            <Timer className="h-3.5 w-3.5" />
            first signal → decision in {duration(o.signal_to_decision_seconds)}
          </p>
        )}
      </div>
      <div className="flex items-center gap-2">
        {DECISIONS.map((d) => (
          <Button
            key={d.key}
            size="sm"
            variant={decision === d.key ? "primary" : "outline"}
            onClick={() => decide.mutate({ opportunityId, data: { decision: d.key } })}
            disabled={decide.isPending}
          >
            {d.label}
          </Button>
        ))}
      </div>
    </Card>
  );
}

export function OpportunityDetail({ opportunityId }: { opportunityId: string }) {
  const qc = useQueryClient();
  const { data: o, isLoading, isError } = useGetOpportunity(opportunityId);
  const screen = useScreen({
    mutation: { onSuccess: () => qc.invalidateQueries() },
  });

  if (isError) {
    return <Card className="p-6 text-sm text-muted-foreground">Decision record not found.</Card>;
  }

  if (isLoading || !o) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-28 w-full rounded-2xl" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-36 rounded-2xl" />
          ))}
        </div>
      </div>
    );
  }

  const byAxis = new Map(o.axes.map((a) => [a.axis, a]));

  return (
    <div>
      <Link
        href="/opportunities"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Decisions
      </Link>

      {/* Header */}
      <Card className="mt-4 p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-semibold tracking-tight text-foreground">
                {o.company_name ?? "Unnamed deal"}
              </h1>
              <Badge variant="muted">{o.status}</Badge>
              {o.decision && <Badge variant="primary">{o.decision}</Badge>}
            </div>
            {o.idea && (
              <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                {o.idea}
              </p>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-subtle">
              {o.sector && <span>{o.sector}</span>}
              {o.geo && <span>{o.geo}</span>}
              <span>logged {relativeTime(o.created_at)}</span>
            </div>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            {o.founder_id && (
              <Link
                href={`/founders/${o.founder_id}`}
                className="inline-flex items-center gap-1.5 rounded-full border border-border-strong bg-surface px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:border-primary hover:text-primary"
              >
                <User className="h-3.5 w-3.5" />
                Founder profile
              </Link>
            )}
            <Button
              size="sm"
              onClick={() => screen.mutate({ opportunityId, params: {} })}
              disabled={screen.isPending}
              title="Score all three axes (LLM idea axis, may take up to a minute)"
            >
              {screen.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Scale className="h-4 w-4" />
              )}
              {screen.isPending ? "Screening…" : "Run screening"}
            </Button>
          </div>
        </div>
      </Card>

      {/* Three-axis screen: scored independently, never averaged */}
      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        {AXIS_ORDER.map((axis) => (
          <AxisScoreCard key={axis} axis={axis} data={byAxis.get(axis)} />
        ))}
      </div>

      {/* Diligence detail */}
      <MarketAnalysis opportunityId={o.id} />

      {/* Investment memo */}
      <MemoSection opportunityId={o.id} />

      {/* Decision — completes the funnel */}
      <DecisionBar o={o} />
    </div>
  );
}
