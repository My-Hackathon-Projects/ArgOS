import type { MarketAnalysisResponse } from "@/api/generated/model";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { TrendIcon, verdictBadge } from "@/components/market/meta";

/** Hero card: opportunity name, sector/geo, Market-axis score + verdict + trend. */
export function AxisCard({ a }: { a: MarketAnalysisResponse }) {
  const axis = a.axis;
  const vb = verdictBadge(axis?.verdict ?? null);

  return (
    <Card className="p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="min-w-0">
          <div className="text-lg font-semibold tracking-tight text-foreground">
            {a.company_name ?? "Opportunity"}
          </div>
          <div className="text-sm text-muted-foreground">
            {a.sector} · {a.geo}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-4xl font-semibold tracking-tight text-foreground">
            {axis?.score ?? "—"}
          </span>
          <div className="flex flex-col items-end gap-1">
            <Badge variant={vb.variant}>{vb.label}</Badge>
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <TrendIcon trend={axis?.trend ?? null} />
              {axis?.trend}
            </span>
          </div>
        </div>
      </div>
      {axis?.rationale && (
        <p className="mt-4 text-[13px] leading-relaxed text-muted-foreground">{axis.rationale}</p>
      )}
    </Card>
  );
}
