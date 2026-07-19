"use client";

import { TrendingUp, TrendingDown, Minus, ExternalLink, AlertTriangle } from "lucide-react";
import {
  useListMarketOpportunities,
  useGetMarketAnalysis,
} from "@/api/generated/default/default";
import type { MarketFigureItem } from "@/api/generated/model";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

function verdictBadge(v: string | null): { variant: BadgeProps["variant"]; label: string } {
  if (v === "bull") return { variant: "success", label: "Bull" };
  if (v === "bear") return { variant: "danger", label: "Bear" };
  return { variant: "muted", label: "Neutral" };
}

function TrendIcon({ trend }: { trend: string | null }) {
  if (trend === "improving") return <TrendingUp className="h-4 w-4 text-emerald-600" />;
  if (trend === "declining") return <TrendingDown className="h-4 w-4 text-rose-600" />;
  return <Minus className="h-4 w-4 text-subtle" />;
}

function Src({ url }: { url: string | null }) {
  if (!url) return null;
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 text-xs text-subtle hover:text-primary"
    >
      source <ExternalLink className="h-3 w-3" />
    </a>
  );
}

function Trust({ value }: { value: number | null }) {
  if (value == null) return null;
  return (
    <span className="text-xs tabular-nums text-subtle">trust {Math.round(value * 100)}%</span>
  );
}

function basisChip(b: string | null) {
  const label = b === "estimated_bottom_up" ? "estimated" : b ?? "—";
  const cls =
    b === "reported"
      ? "text-emerald-700 bg-emerald-50"
      : b === "estimated_bottom_up"
        ? "text-amber-700 bg-amber-50"
        : "text-subtle bg-muted";
  return (
    <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${cls}`}>{label}</span>
  );
}

function FigureCard({ f }: { f: MarketFigureItem }) {
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs uppercase tracking-wider text-subtle">{f.metric}</span>
        {basisChip(f.basis)}
      </div>
      <div className="mt-2 font-serif text-2xl text-foreground">{f.value ?? "not found"}</div>
      <div className="mt-1.5 flex items-center gap-3">
        <Trust value={f.trust_score} />
        <Src url={f.url} />
      </div>
    </Card>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-8">
      <h3 className="mb-3 text-sm font-semibold text-foreground">{title}</h3>
      {children}
    </div>
  );
}

export function MarketView() {
  const list = useListMarketOpportunities();
  const oppId = list.data?.[0]?.id;
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
  const axis = a.axis;
  const vb = verdictBadge(axis?.verdict ?? null);

  return (
    <div>
      {/* Market axis */}
      <Card className="p-6">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-lg font-semibold text-foreground">
              {a.company_name ?? "Opportunity"}
            </div>
            <div className="text-sm text-muted-foreground">
              {a.sector} · {a.geo}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="font-serif text-3xl text-foreground">{axis?.score ?? "—"}</span>
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

      {/* Market sizing */}
      {a.sizing.length > 0 && (
        <Section title="Market sizing">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {a.sizing.map((f) => (
              <FigureCard key={f.metric} f={f} />
            ))}
          </div>
        </Section>
      )}

      {/* Comparables */}
      {a.comparables.length > 0 && (
        <Section title="Comparables (raised)">
          <div className="space-y-2">
            {a.comparables.map((c) => (
              <Card key={c.name} className="flex items-start justify-between gap-4 p-4">
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
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <Trust value={c.trust_score} />
                  <Src url={c.url} />
                </div>
              </Card>
            ))}
          </div>
        </Section>
      )}

      {/* Competition */}
      {a.competitors.length > 0 && (
        <Section title="Competition">
          <div className="space-y-2">
            {a.competitors.map((c) => (
              <Card key={c.name} className="flex items-start justify-between gap-4 p-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                    {c.name}
                    {c.cluster && (
                      <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-subtle">
                        {c.cluster}
                      </span>
                    )}
                    {c.is_emerging_threat && (
                      <Badge variant="danger">threat</Badge>
                    )}
                  </div>
                  {c.positioning && (
                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                      {c.positioning}
                    </p>
                  )}
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <Trust value={c.trust_score} />
                  <Src url={c.url} />
                </div>
              </Card>
            ))}
          </div>
        </Section>
      )}

      {/* KPI benchmarks */}
      {a.kpi.length > 0 && (
        <Section title="KPI benchmarks">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {a.kpi.map((f) => (
              <FigureCard key={f.metric} f={f} />
            ))}
          </div>
        </Section>
      )}

      {/* Gaps — honestly flagged */}
      {axis && axis.gaps.length > 0 && (
        <Section title="Flagged gaps">
          <Card className="p-4">
            <ul className="space-y-1.5">
              {axis.gaps.map((g, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-muted-foreground">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
                  {g}
                </li>
              ))}
            </ul>
          </Card>
        </Section>
      )}
    </div>
  );
}
