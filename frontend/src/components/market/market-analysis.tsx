"use client";

import { useGetMarketAnalysis } from "@/api/generated/default/default";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ComparableCard, CompetitorCard } from "@/components/market/entity-cards";
import { FigureCard } from "@/components/market/figure-card";
import { GapsCard } from "@/components/market/gaps-card";
import { Section } from "@/components/market/section";

/** Full market research block for one opportunity: sizing, comparables,
 *  competition, KPI benchmarks, and flagged gaps. Embedded in the opportunity
 *  detail page under the three-axis scores. */
export function MarketAnalysis({ opportunityId }: { opportunityId: string }) {
  const { data: a, isLoading, isError } = useGetMarketAnalysis(opportunityId);

  if (isLoading) {
    return (
      <div className="mt-8 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-28 rounded-2xl" />
        ))}
      </div>
    );
  }

  if (isError || !a) {
    return (
      <Section title="Market research">
        <Card className="p-5 text-sm text-muted-foreground">
          No market analysis yet for this opportunity. Run the market-research agent
          (<code className="text-foreground">app.market.service.run_market_analysis</code>) to
          fill sizing, competition, comparables and the Market axis.
        </Card>
      </Section>
    );
  }

  return (
    <div>
      {a.axis?.rationale && (
        <Section title="Market rationale">
          <Card className="p-5">
            <p className="text-[13px] leading-relaxed text-muted-foreground">
              {a.axis.rationale}
            </p>
          </Card>
        </Section>
      )}

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
