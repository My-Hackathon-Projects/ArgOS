import { Container } from "@/components/ui/container";
import { PageHeader } from "@/components/ui/page-header";
import { ApplyButton } from "@/components/inbound/apply-dialog";
import { InboundView } from "@/components/inbound/inbound-view";

export default function InboundPage() {
  return (
    <Container className="max-w-4xl">
      <PageHeader
        eyebrow="Inbound"
        title="Applications"
        subtitle="Deals that come to you by email: founders send their pitch deck and company name, the intake agent extracts the details, and every application lands here in the screening loop."
        actions={<ApplyButton />}
      />
      <div className="mt-10">
        <InboundView />
      </div>
    </Container>
  );
}
