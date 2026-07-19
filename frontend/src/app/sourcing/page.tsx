import { Container } from "@/components/ui/container";
import { PageHeader } from "@/components/ui/page-header";
import { Card } from "@/components/ui/card";
import { SignalFeed } from "@/components/sourcing/signal-feed";
import { ChannelList } from "@/components/sourcing/channel-list";
import { DiscoveryButton } from "@/components/sourcing/discovery-button";

export default function SourcingPage() {
  return (
    <Container>
      <PageHeader
        eyebrow="Sourcing"
        title="Detect founders before they show up"
        subtitle="A live footprint of founders to be: papers, launches, repos and profiles surfacing across the open web, resolved to people."
        actions={<DiscoveryButton />}
        accent="#0071e3"
      />

      <div className="mt-10 grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
        <section aria-label="Signal feed">
          <SignalFeed />
        </section>
        <aside className="lg:sticky lg:top-[4.5rem] lg:self-start">
          <Card className="p-3">
            <ChannelList />
          </Card>
        </aside>
      </div>
    </Container>
  );
}
