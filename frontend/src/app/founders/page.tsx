import { PageHeader } from "@/components/ui/page-header";
import { FoundersTable } from "@/components/founders/founders-table";

export default function FoundersPage() {
  return (
    <div className="mx-auto max-w-5xl px-8 py-8">
      <PageHeader
        eyebrow="Founders"
        title="Discovered people"
        subtitle="Every person resolved from the signal feed. The Founder Score follows the person — across whatever they build next."
      />
      <div className="mt-8">
        <FoundersTable />
      </div>
    </div>
  );
}
