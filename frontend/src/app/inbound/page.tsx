import { Container } from "@/components/ui/container";
import { PageHeader } from "@/components/ui/page-header";
import { InboundView } from "@/components/inbound/inbound-view";

export default function InboundPage() {
  return (
    <Container className="max-w-4xl">
      <PageHeader
        eyebrow="Inbound"
        title="Applications"
        subtitle="Deals that come to you: founders applying, warm intros, and deals logged by hand. Each application becomes an opportunity in the screening loop."
      />
      <div className="mt-10">
        <InboundView />
      </div>
    </Container>
  );
}
