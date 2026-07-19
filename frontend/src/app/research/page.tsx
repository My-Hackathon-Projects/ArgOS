import { Container } from "@/components/ui/container";
import { PageHeader } from "@/components/ui/page-header";
import { MarketView } from "@/components/market/market-view";

export default function ResearchPage() {
  return (
    <Container className="max-w-5xl">
      <PageHeader
        eyebrow="Agent"
        title="Market research"
        subtitle="TAM/SAM/SOM, competition, comparable rounds and KPI benchmarks — web-researched, cited, and gap-flagged. Feeds the Market axis + memo."
      />
      <div className="mt-10">
        <MarketView />
      </div>
    </Container>
  );
}
