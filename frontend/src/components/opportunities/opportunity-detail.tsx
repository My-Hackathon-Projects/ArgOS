"use client";

import { ExternalLink, Minus, TrendingDown, TrendingUp } from "lucide-react";
import {
  useCreateMemo,
  useGetMemo,
  useGetOpportunity,
  useScreen,
} from "@/api/generated/default/default";
import type { OpportunityAxisSummary } from "@/api/generated/model";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

const AXIS_LABEL: Record<string, string> = {
  founder: "Founder",
  market: "Market",
  idea: "Idea vs Market",
};

function verdictVariant(v: string): BadgeProps["variant"] {
  if (v === "bull") return "success";
  if (v === "bear") return "danger";
  return "outline";
}

function Trend({ trend }: { trend: string }) {
  const Icon = trend === "improving" ? TrendingUp : trend === "declining" ? TrendingDown : Minus;
  return (
    <span className="inline-flex items-center gap-1 text-xs text-subtle">
      <Icon className="h-3.5 w-3.5" />
      {trend}
    </span>
  );
}

function Urls({ urls }: { urls: unknown }) {
  const list = Array.isArray(urls) ? (urls as string[]) : [];
  if (list.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {list.slice(0, 6).map((u, i) => (
        <a
          key={i}
          href={u}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 rounded-full border border-border-strong px-2 py-0.5 text-[11px] text-muted-foreground hover:border-primary hover:text-primary"
        >
          <ExternalLink className="h-3 w-3" />
          source
        </a>
      ))}
    </div>
  );
}

function AxisCard({ a }: { a: OpportunityAxisSummary }) {
  const ev = (a.evidence ?? {}) as Record<string, unknown>;
  return (
    <Card className="flex flex-col gap-2 p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-foreground">{AXIS_LABEL[a.axis] ?? a.axis}</h3>
        <Badge variant={verdictVariant(a.verdict)}>{a.verdict}</Badge>
      </div>
      <div className="flex items-baseline gap-2">
        <span className="font-serif text-2xl text-foreground">
          {a.score != null ? Math.round(a.score) : "—"}
        </span>
        <Trend trend={a.trend} />
        {a.confidence != null && (
          <span className="ml-auto text-xs text-subtle">conf {Math.round(a.confidence * 100)}%</span>
        )}
      </div>
      {a.rationale && (
        <p className="text-[13px] leading-relaxed text-muted-foreground">{a.rationale}</p>
      )}
      {a.gaps && a.gaps.length > 0 && (
        <ul className="mt-1 space-y-0.5">
          {a.gaps.map((g, i) => (
            <li key={i} className="text-[11px] text-amber-700">
              ⚠ {g}
            </li>
          ))}
        </ul>
      )}
      <Urls urls={ev.urls} />
    </Card>
  );
}

type Hypothesis = { statement: string; evidence_claim_ids: string[] };

function Memo({ opportunityId }: { opportunityId: string }) {
  const { data: memo, isLoading, isError } = useGetMemo(opportunityId);
  const create = useCreateMemo();

  if (isLoading) return <Skeleton className="h-48 w-full rounded-2xl" />;
  if (isError || !memo) {
    return (
      <Card className="flex items-center justify-between p-5">
        <p className="text-sm text-muted-foreground">No memo generated yet.</p>
        <Button
          onClick={() => create.mutate({ opportunityId })}
          disabled={create.isPending}
        >
          {create.isPending ? "Generating…" : "Generate memo"}
        </Button>
      </Card>
    );
  }

  const s = (memo.sections ?? {}) as Record<string, unknown>;
  const hyps = (s.hypotheses as Hypothesis[]) ?? [];
  const swot = (s.swot as Record<string, string[]>) ?? {};
  const q = (memo.quality ?? {}) as Record<string, unknown>;
  const provUrls = Array.isArray(q.provenance_urls) ? (q.provenance_urls as string[]) : [];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h2 className="font-serif text-xl text-foreground">Investment memo</h2>
        {q.all_citations_resolved === true && <Badge variant="success">citations resolved</Badge>}
        <span className="text-xs text-subtle">{provUrls.length} sources</span>
      </div>

      {typeof s.snapshot === "string" && (
        <Card className="p-5">
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-subtle">Snapshot</h3>
          <p className="text-sm leading-relaxed text-foreground">{s.snapshot}</p>
        </Card>
      )}

      {hyps.length > 0 && (
        <Card className="p-5">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-subtle">
            Investment hypotheses
          </h3>
          <ul className="space-y-2">
            {hyps.map((h, i) => (
              <li key={i} className="text-sm leading-relaxed text-foreground">
                <span className="mr-1 text-primary">•</span>
                {h.statement}
                <span className="ml-1 text-[11px] text-subtle">
                  [{h.evidence_claim_ids?.length ?? 0} cited]
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        {(["strengths", "weaknesses", "opportunities", "threats"] as const).map((k) => (
          <Card key={k} className="p-4">
            <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-subtle">{k}</h4>
            <ul className="space-y-0.5">
              {(swot[k] ?? []).map((b, i) => (
                <li key={i} className="text-[13px] text-muted-foreground">
                  {b}
                </li>
              ))}
            </ul>
          </Card>
        ))}
      </div>

      <Card className="border-l-2 border-l-primary p-5">
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-subtle">
          Recommendation
          {memo.confidence != null && (
            <span className="ml-2 font-normal text-subtle">
              confidence {Math.round(memo.confidence * 100)}%
            </span>
          )}
        </h3>
        <p className="text-sm leading-relaxed text-foreground">{memo.recommendation}</p>
      </Card>

      {memo.gaps.length > 0 && (
        <Card className="p-5">
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-subtle">
            Flagged gaps (honest about what we don&apos;t know)
          </h3>
          <ul className="space-y-0.5">
            {memo.gaps.map((g, i) => (
              <li key={i} className="text-[13px] text-amber-700">
                ⚠ {g}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Urls urls={provUrls} />
    </div>
  );
}

export function OpportunityDetail({ opportunityId }: { opportunityId: string }) {
  const { data: opp, isLoading, isError, refetch } = useGetOpportunity(opportunityId);
  const screen = useScreen();

  if (isError) return <Card className="p-6 text-sm text-muted-foreground">Opportunity not found.</Card>;
  if (isLoading || !opp) return <Skeleton className="h-64 w-full rounded-2xl" />;

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 className="font-serif text-2xl text-foreground">
              {opp.company_name ?? "Opportunity"}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">{opp.idea}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-subtle">
              {opp.sector && <Badge variant="muted">{opp.sector}</Badge>}
              {opp.geo && <span>{opp.geo}</span>}
              <Badge variant="primary">{opp.status}</Badge>
            </div>
          </div>
          {opp.axes.length === 0 && (
            <Button
              onClick={() => screen.mutate({ opportunityId }, { onSuccess: () => refetch() })}
              disabled={screen.isPending}
            >
              {screen.isPending ? "Screening…" : "Run 3-axis screen"}
            </Button>
          )}
        </div>
      </Card>

      {opp.axes.length > 0 && (
        <div>
          <h2 className="mb-1 font-serif text-xl text-foreground">3-axis screen</h2>
          <p className="mb-3 text-xs text-subtle">
            Scored independently — never averaged. The disagreement is the signal.
          </p>
          <div className="grid gap-3 md:grid-cols-3">
            {opp.axes.map((a) => (
              <AxisCard key={a.axis} a={a} />
            ))}
          </div>
        </div>
      )}

      <Memo opportunityId={opportunityId} />
    </div>
  );
}
