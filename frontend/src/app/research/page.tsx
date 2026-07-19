import { ArrowUpRight, TrendingUp, TrendingDown } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

// Aspirational preview — not wired to a backend yet. Shows the intended shape of the
// market-research agent (pricing benchmarks, KPIs, findings) so the UI direction is legible.

const KPIS = [
  { label: "Median seed check", value: "$1.4M", delta: "+12%", up: true },
  { label: "Pre-money benchmark", value: "$8.2M", delta: "+5%", up: true },
  { label: "Sector momentum", value: "High", delta: "AI infra", up: true },
  { label: "Comparable rounds (90d)", value: "37", delta: "-8%", up: false },
];

const FINDINGS = [
  {
    title: "Applied-ML tooling is repricing upward",
    body: "Median pre-money for seed-stage ML infrastructure has drifted ~15% higher over two quarters, led by eval/observability startups.",
  },
  {
    title: "Academic-origin teams close faster",
    body: "Founders sourced from research labs reach a priced round ~3 weeks sooner than the cohort median once a first cheque appears.",
  },
  {
    title: "German technical hubs are underpriced",
    body: "Munich/Tübingen technical founders show comparable traction to Bay Area peers at a 20–30% valuation discount.",
  },
];

export default function ResearchPage() {
  return (
    <div className="mx-auto max-w-5xl px-8 py-8">
      <PageHeader
        eyebrow="Agent"
        title="Market research"
        subtitle="Pricing benchmarks, sector momentum and comparable rounds — grounded in the founders you're tracking."
        actions={<Badge variant="outline">Preview</Badge>}
      />

      <div
        className="mt-8 overflow-hidden rounded-3xl p-8 text-white"
        style={{
          background:
            "radial-gradient(120% 140% at 0% 0%, #6366f1 0%, #8b5cf6 42%, #ec4899 100%)",
        }}
      >
        <div className="max-w-xl">
          <div className="text-xs font-medium uppercase tracking-[0.14em] text-white/70">
            This week
          </div>
          <h2 className="mt-2 font-serif text-3xl leading-tight">
            AI-infrastructure seed pricing is running hot
          </h2>
          <p className="mt-3 text-sm leading-relaxed text-white/80">
            Valuations for technical, research-origin teams are outpacing the broader seed market.
            The window on underpriced European technical talent is still open.
          </p>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {KPIS.map((k) => (
          <Card key={k.label} className="p-5">
            <div className="text-xs text-muted-foreground">{k.label}</div>
            <div className="mt-2 font-serif text-2xl text-foreground">{k.value}</div>
            <div
              className={`mt-1 inline-flex items-center gap-1 text-xs ${k.up ? "text-emerald-600" : "text-rose-600"}`}
            >
              {k.up ? (
                <TrendingUp className="h-3.5 w-3.5" />
              ) : (
                <TrendingDown className="h-3.5 w-3.5" />
              )}
              {k.delta}
            </div>
          </Card>
        ))}
      </div>

      <h3 className="mt-8 mb-4 text-sm font-semibold text-foreground">Findings</h3>
      <div className="space-y-3">
        {FINDINGS.map((f) => (
          <Card key={f.title} className="flex items-start justify-between gap-4 p-5">
            <div>
              <div className="text-sm font-medium text-foreground">{f.title}</div>
              <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">{f.body}</p>
            </div>
            <ArrowUpRight className="h-4 w-4 shrink-0 text-subtle" />
          </Card>
        ))}
      </div>

      <p className="mt-6 text-xs text-subtle">
        Preview — illustrative figures. This view is not yet wired to live data.
      </p>
    </div>
  );
}
