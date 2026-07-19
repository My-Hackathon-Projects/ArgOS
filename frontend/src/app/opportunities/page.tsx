import { Container } from "@/components/ui/container";
import { PageHeader } from "@/components/ui/page-header";
import { OpportunitiesList } from "@/components/opportunities/opportunities-list";

export default function OpportunitiesPage() {
  return (
    <Container className="max-w-4xl">
      <PageHeader
        eyebrow="Screening"
        title="Opportunities"
        subtitle="Every deal in the screening loop, scored on three axes: founder, market, and idea versus market. Open one for the full diligence detail and memo."
      />
      <div className="mt-10">
        <OpportunitiesList />
      </div>
    </Container>
  );
}
