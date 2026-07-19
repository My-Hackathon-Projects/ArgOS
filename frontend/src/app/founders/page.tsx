import { Container } from "@/components/ui/container";
import { PageHeader } from "@/components/ui/page-header";
import { FounderSearch } from "@/components/founders/founder-search";
import { FoundersTable } from "@/components/founders/founders-table";

export default function FoundersPage() {
  return (
    <Container className="max-w-5xl">
      <PageHeader
        eyebrow="Founders"
        title="Discovered people"
        subtitle="Every person resolved from the signal feed. The Founder Score follows the person, across whatever they build next."
        accent="#7c3aed"
        aura="constellation"
      />
      <div className="mt-10">
        <FounderSearch />
        <FoundersTable />
      </div>
    </Container>
  );
}
