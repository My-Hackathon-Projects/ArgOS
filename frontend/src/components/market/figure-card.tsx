import type { MarketFigureItem } from "@/api/generated/model";
import { Card } from "@/components/ui/card";
import { BasisChip, Src, Trust } from "@/components/market/meta";

/** One market figure (TAM, CAC, ...) with its basis chip, trust and source. */
export function FigureCard({ f }: { f: MarketFigureItem }) {
  return (
    <Card className="card-shadow-hover p-4 transition-shadow duration-300">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-xs uppercase tracking-wider text-subtle">{f.metric}</span>
        <BasisChip basis={f.basis} />
      </div>
      <div className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
        {f.value ?? "not found"}
      </div>
      <div className="mt-1.5 flex items-center gap-3">
        <Trust value={f.trust_score} />
        <Src url={f.url} />
      </div>
    </Card>
  );
}
