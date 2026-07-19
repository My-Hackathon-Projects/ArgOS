"use client";

import { useState } from "react";
import {
  useGetMarketAnalysis,
  useListMarketOpportunities,
} from "@/api/generated/default/default";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AxisCard } from "@/components/market/axis-card";
import { ComparableCard, CompetitorCard } from "@/components/market/entity-cards";
import { FigureCard } from "@/components/market/figure-card";
import { GapsCard } from "@/components/market/gaps-card";
import { OpportunityPicker } from "@/components/market/opportunity-picker";
import { Section } from "@/components/market/section";

function LoadingState() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-40 w-full rounded-3xl" />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-28 rounded-2xl" />
        ))}
      </div>
    </div>
  );
}

export function MarketView() {
  const list = useListMarketOpportunities();
  const [picked, setPicked] = useState<string | null>(null);
  const oppId = picked ?? list.data?.[0]?.id ?? null;
  const analysis = useGetMarketAnalysis(oppId ?? "", { query: { enabled: !!oppId } });

  if (list.isError) {
    return (
      <Card className="p-6 text-sm text-muted-foreground">
        Could not load market research. Is the backend running on{" "}
        <code className="text-foreground">localhost:8000</code>?
      </Card>
    );
  }

  if (list.isLoading || (oppId && analysis.isLoading)) {
    return <LoadingState />;
  }

  if (!oppId || !analysis.data) {
    return (
      <Card className="p-6 text-sm text-muted-foreground">
        No market analysis yet. Run the market-research agent on an opportunity
        (<code className="text-foreground">app.market.service.run_market_analysis</code>) to
        populate this view.
      </Card>
    );
  }

  const a = analysis.data;

  return (
    <div>
      <OpportunityPicker items={list.data ?? []} selectedId={oppId} onSelect={setPicked} />

      <AxisCard a={a} />

      {a.sizing.length > 0 && (
        <Section title="Market sizing">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {a.sizing.map((f) => (
              <FigureCard key={f.metric} f={f} />
            ))}
          </div>
        </Section>
      )}

      {a.comparables.length > 0 && (
        <Section title="Comparables (raised)">
          <div className="space-y-2">
            {a.comparables.map((c) => (
              <ComparableCard key={c.name} c={c} />
            ))}
          </div>
        </Section>
      )}

      {a.competitors.length > 0 && (
        <Section title="Competition">
          <div className="space-y-2">
            {a.competitors.map((c) => (
              <CompetitorCard key={c.name} c={c} />
            ))}
          </div>
        </Section>
      )}

      {a.kpi.length > 0 && (
        <Section title="KPI benchmarks">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {a.kpi.map((f) => (
              <FigureCard key={f.metric} f={f} />
            ))}
          </div>
        </Section>
      )}

      {a.axis && a.axis.gaps.length > 0 && (
        <Section title="Flagged gaps">
          <GapsCard gaps={a.axis.gaps} />
        </Section>
      )}
    </div>
  );
}
