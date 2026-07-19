import type { MarketComparableItem, MarketCompetitorItem } from "@/api/generated/model";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Src, Trust } from "@/components/market/meta";

/** List rows for comparables (companies that raised) and competitors. */

export function ComparableCard({ c }: { c: MarketComparableItem }) {
  return (
    <Card className="card-shadow-hover flex flex-col gap-3 p-4 transition-shadow duration-300 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
      <div className="min-w-0">
        <div className="text-sm font-medium text-foreground">
          {c.name}
          <span className="ml-2 text-xs text-muted-foreground">
            {c.round_size ?? "undisclosed"} · {c.stage ?? "stage n/a"}
            {c.date ? ` · ${c.date}` : ""}
          </span>
        </div>
        {c.similarity_rationale && (
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            {c.similarity_rationale}
          </p>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-3 sm:flex-col sm:items-end sm:gap-1">
        <Trust value={c.trust_score} />
        <Src url={c.url} />
      </div>
    </Card>
  );
}

export function CompetitorCard({ c }: { c: MarketCompetitorItem }) {
  return (
    <Card className="card-shadow-hover flex flex-col gap-3 p-4 transition-shadow duration-300 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2 text-sm font-medium text-foreground">
          {c.name}
          {c.cluster && (
            <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-subtle">
              {c.cluster}
            </span>
          )}
          {c.is_emerging_threat && <Badge variant="danger">threat</Badge>}
        </div>
        {c.positioning && (
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{c.positioning}</p>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-3 sm:flex-col sm:items-end sm:gap-1">
        <Trust value={c.trust_score} />
        <Src url={c.url} />
      </div>
    </Card>
  );
}
