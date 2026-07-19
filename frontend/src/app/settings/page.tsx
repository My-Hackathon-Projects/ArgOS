import { Container } from "@/components/ui/container";
import { PageHeader } from "@/components/ui/page-header";
import { ThesisView } from "@/components/settings/thesis-view";

export default function SettingsPage() {
  return (
    <Container className="max-w-3xl">
      <PageHeader
        eyebrow="Configuration"
        title="Investment thesis"
        subtitle="The lens that drives discovery: sectors, stage, geography, and the founder traits worth chasing."
      />
      <div className="mt-10">
        <ThesisView />
      </div>
    </Container>
  );
}
