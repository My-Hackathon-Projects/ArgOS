import { PageHeader } from "@/components/ui/page-header";
import { MarketView } from "@/components/market/market-view";

export default function ResearchPage() {
  return (
    <div className="mx-auto max-w-5xl px-8 py-8">
      <PageHeader
        eyebrow="Agent"
        title="Market research"
        subtitle="TAM/SAM/SOM, competition, comparable rounds and KPI benchmarks — web-researched, cited, and gap-flagged. Feeds the Market axis + memo."
      />
      <div className="mt-8">
        <MarketView />
      </div>
    </div>
  );
}
