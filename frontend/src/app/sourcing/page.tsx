import { Container } from "@/components/ui/container";
import { PageHeader } from "@/components/ui/page-header";
import { Card } from "@/components/ui/card";
import { SignalFeed } from "@/components/sourcing/signal-feed";
import { ChannelList } from "@/components/sourcing/channel-list";

export default function SourcingPage() {
  return (
    <Container>
      <PageHeader
        eyebrow="Sourcing"
        title="Detect founders before they show up"
        subtitle="A live footprint of founders to be: papers, launches, repos and profiles surfacing across the open web, resolved to people."
        actions={
          <span className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1.5 text-xs text-muted-foreground">
            <span className="relative flex h-2 w-2" aria-hidden>
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            </span>
            Discovery agent runs continuously in the background
          </span>
        }
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
