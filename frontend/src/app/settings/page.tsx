import { PageHeader } from "@/components/ui/page-header";
import { ThesisView } from "@/components/settings/thesis-view";

export default function SettingsPage() {
  return (
    <div className="mx-auto max-w-3xl px-8 py-8">
      <PageHeader
        eyebrow="Configuration"
        title="Investment thesis"
        subtitle="The lens that drives discovery — sectors, stage, geography, and the founder traits worth chasing."
      />
      <div className="mt-8">
        <ThesisView />
      </div>
    </div>
  );
}
